@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在打包 DelayScope UI 工具...
rem 防止 exe 占用导致 WinError 5
taskkill /im DelayScope.exe /f >nul 2>nul
taskkill /im DelayCalcTool.exe /f >nul 2>nul
python -m pip install numpy matplotlib customtkinter pyinstaller -q
python -m PyInstaller build_exe.spec --noconfirm
if %ERRORLEVEL% equ 0 (
    echo.
    rem 清理历史残留的空 log 目录（工具本身不需要）
    if exist "dist\log" (
        rmdir /s /q "dist\log"
    )
    echo 打包完成。可执行文件: dist\DelayScope.exe
    explorer dist
) else (
    echo 打包失败。
    pause
)
