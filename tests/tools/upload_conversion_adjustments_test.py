"""Test cases for the upload_conversion_adjustments tool (LensShop).

Nothing here calls the Google Ads API: the client and services are mocked, so
no adjustment is ever sent.
"""

import unittest
from unittest.mock import MagicMock, patch

from ads_mcp.tools import mutate

CUSTOMER = '5521940727'
ACTION = '7691672097'
WHEN = '2026-11-12 14:00:00-03:00'


def _row(order_id='4109', kind='RETRACTION', **extra):
    row = {
        'order_id': order_id,
        'adjustment_type': kind,
        'adjustment_date_time': WHEN,
    }
    row.update(extra)
    return row


def _failure_status(client, errors):
    """Builds a fake partial_failure_error carrying {index: message}."""
    status = MagicMock()
    details = []
    failures = {}
    for n, (idx, msg) in enumerate(errors.items()):
        key = f'detail-{n}'
        details.append(MagicMock(value=key))
        el = MagicMock(field_name='conversion_adjustments', index=idx)
        err = MagicMock(message=msg)
        err.location.field_path_elements = [el]
        failures[key] = MagicMock(errors=[err])
    status.details = details

    class FakeFailure:
        @staticmethod
        def deserialize(value):
            return failures[value]

    client.get_type.side_effect = lambda name: (
        FakeFailure() if name == 'GoogleAdsFailure' else MagicMock()
    )
    return status


class TestValidateRows(unittest.TestCase):
    def test_valid_retraction(self):
        self.assertIsNone(mutate._validate_adjustment_row(_row(), 0))

    def test_valid_restatement(self):
        row = _row(kind='RESTATEMENT', restatement_value=179.9)
        self.assertIsNone(mutate._validate_adjustment_row(row, 0))

    def test_missing_order_id(self):
        self.assertIn(
            'order_id', mutate._validate_adjustment_row(_row(order_id=' '), 3)
        )

    def test_bad_type(self):
        self.assertIn(
            'adjustment_type',
            mutate._validate_adjustment_row(_row(kind='ENHANCEMENT'), 0),
        )

    def test_date_needs_timezone(self):
        row = _row()
        row['adjustment_date_time'] = '2026-11-12 14:00:00'
        self.assertIn(
            'adjustment_date_time', mutate._validate_adjustment_row(row, 0)
        )

    def test_retraction_rejects_value(self):
        self.assertIn(
            'RETRACTION',
            mutate._validate_adjustment_row(_row(restatement_value=1), 0),
        )

    def test_restatement_requires_value(self):
        self.assertIn(
            'restatement_value',
            mutate._validate_adjustment_row(_row(kind='RESTATEMENT'), 0),
        )

    def test_restatement_rejects_negative_or_text(self):
        for bad in (-1, 'abc'):
            row = _row(kind='RESTATEMENT', restatement_value=bad)
            self.assertIsNotNone(mutate._validate_adjustment_row(row, 0))


class TestUploadConversionAdjustments(unittest.TestCase):
    def _run(self, adjustments, errors=None, **kwargs):
        client = MagicMock()
        service = MagicMock()
        response = MagicMock()
        response.partial_failure_error = (
            _failure_status(client, errors) if errors else None
        )
        service.upload_conversion_adjustments.return_value = response
        request = MagicMock()
        request.conversion_adjustments = MagicMock()
        if not errors:
            client.get_type.side_effect = lambda name: (
                request if name == 'UploadConversionAdjustmentsRequest'
                else MagicMock()
            )
        with patch('ads_mcp.utils.get_googleads_client', return_value=client), \
             patch('ads_mcp.utils.get_googleads_service', return_value=service):
            out = mutate.upload_conversion_adjustments(
                CUSTOMER, ACTION, adjustments, **kwargs
            )
        return out, service, client

    def test_default_is_validate_only(self):
        client = MagicMock()
        service = MagicMock()
        service.upload_conversion_adjustments.return_value.partial_failure_error = None
        request = MagicMock()
        client.get_type.side_effect = lambda name: (
            request if name == 'UploadConversionAdjustmentsRequest'
            else MagicMock()
        )
        with patch('ads_mcp.utils.get_googleads_client', return_value=client), \
             patch('ads_mcp.utils.get_googleads_service', return_value=service):
            out = mutate.upload_conversion_adjustments(
                CUSTOMER, ACTION, [_row()]
            )
        self.assertIs(request.validate_only, True)
        self.assertIs(request.partial_failure, True)
        self.assertIn('nada foi alterado', out)
        self.assertIn('ACEITA [0] 4109 RETRACTION', out)

    def test_explicit_real_send_flag(self):
        client = MagicMock()
        service = MagicMock()
        service.upload_conversion_adjustments.return_value.partial_failure_error = None
        request = MagicMock()
        client.get_type.side_effect = lambda name: (
            request if name == 'UploadConversionAdjustmentsRequest'
            else MagicMock()
        )
        with patch('ads_mcp.utils.get_googleads_client', return_value=client), \
             patch('ads_mcp.utils.get_googleads_service', return_value=service):
            out = mutate.upload_conversion_adjustments(
                CUSTOMER, ACTION, [_row()], validate_only=False
            )
        self.assertIs(request.validate_only, False)
        self.assertIn('ENVIO REAL', out)

    def test_invalid_input_sends_nothing(self):
        out, service, _ = self._run([_row(), _row(order_id='')])
        self.assertIn('Nada enviado', out)
        self.assertIn('linha 1', out)
        service.upload_conversion_adjustments.assert_not_called()

    def test_empty_list_sends_nothing(self):
        out, service, _ = self._run([])
        self.assertIn('Nada enviado', out)
        service.upload_conversion_adjustments.assert_not_called()

    def test_too_many_rows(self):
        rows = [_row(order_id=str(i)) for i in range(2001)]
        out, service, _ = self._run(rows)
        self.assertIn('no maximo 2000', out)
        service.upload_conversion_adjustments.assert_not_called()

    def test_partial_failure_reports_per_row(self):
        rows = [_row('1'), _row('2'), _row('3')]
        out, _, _ = self._run(rows, errors={1: 'Conversao nao encontrada'})
        self.assertIn('2 de 3 aceita(s), 1 com erro', out)
        self.assertIn('ACEITA [0] 1 RETRACTION', out)
        self.assertIn('ERRO   [1] 2 RETRACTION: Conversao nao encontrada', out)
        self.assertIn('ACEITA [2] 3 RETRACTION', out)

    def test_numeric_action_builds_resource_name(self):
        self.assertEqual(
            mutate._resolve_conversion_action_resource(CUSTOMER, ACTION),
            f'customers/{CUSTOMER}/conversionActions/{ACTION}',
        )

    def test_action_name_must_match_exactly_one(self):
        service = MagicMock()
        service.search.return_value = []
        with patch('ads_mcp.utils.get_googleads_service', return_value=service):
            with self.assertRaises(ValueError):
                mutate._resolve_conversion_action_resource(
                    CUSTOMER, "SHOPIFY - COMPRAS"
                )

    def test_action_name_quote_is_escaped(self):
        service = MagicMock()
        row = MagicMock()
        row.conversion_action.resource_name = 'customers/1/conversionActions/2'
        service.search.return_value = [row]
        with patch('ads_mcp.utils.get_googleads_service', return_value=service):
            mutate._resolve_conversion_action_resource(CUSTOMER, "O'Neil")
        query = service.search.call_args.kwargs['query']
        self.assertIn("O\\'Neil", query)

    def test_tool_is_registered(self):
        from ads_mcp.coordinator import mcp
        import asyncio

        tools = asyncio.run(mcp.list_tools())
        names = [t.name for t in tools]
        self.assertIn('upload_conversion_adjustments', names)


if __name__ == '__main__':
    unittest.main()
