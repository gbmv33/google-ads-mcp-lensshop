@echo off
echo === Sincronizando com o repositorio original (googleads/google-ads-mcp) ===

git fetch upstream
if %errorlevel% neq 0 (echo ERRO: falha ao buscar atualizacoes & pause & exit /b 1)

git checkout main
git merge upstream/main --ff-only
if %errorlevel% neq 0 (echo ERRO: conflito no merge do main & pause & exit /b 1)

git push origin main
if %errorlevel% neq 0 (echo ERRO: falha ao push do main & pause & exit /b 1)

git checkout lensshop/mutate-tools
git rebase main
if %errorlevel% neq 0 (
    echo.
    echo ATENCAO: Conflito no rebase. Resolva manualmente:
    echo   1. Edite os arquivos em conflito
    echo   2. git add .
    echo   3. git rebase --continue
    echo   4. git push origin lensshop/mutate-tools --force-with-lease
    pause
    exit /b 1
)

git push origin lensshop/mutate-tools --force-with-lease
if %errorlevel% neq 0 (echo ERRO: falha ao push do branch & pause & exit /b 1)

echo.
echo === Sincronizacao concluida com sucesso! ===
pause
