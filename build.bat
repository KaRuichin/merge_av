@echo off
REM ============================================================
REM  merge_av Windows 构建脚本
REM  将 merge_av.py 打包为独立的 merge_av.exe
REM ============================================================

echo.
echo ========================================
echo   merge_av - Windows Build Script
echo ========================================
echo.

REM 检查虚拟环境
if exist ".venv\Scripts\activate.bat" (
    echo [1/4] 激活虚拟环境...
    call .venv\Scripts\activate.bat
) else (
    echo [1/4] 未找到虚拟环境，使用系统 Python
)

REM 检查 PyInstaller
echo [2/4] 检查 PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo   PyInstaller 未安装，正在安装...
    pip install pyinstaller
    if errorlevel 1 (
        echo   错误: PyInstaller 安装失败
        pause
        exit /b 1
    )
)

REM 清理旧构建
echo [3/4] 清理旧构建文件...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM 执行构建
echo [4/4] 开始构建 merge_av.exe...
echo.
pyinstaller merge_av.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo   错误: 构建失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   构建完成!
echo   输出文件: dist\merge_av.exe
echo ========================================
echo.

REM 显示文件信息
if exist "dist\merge_av.exe" (
    for %%A in ("dist\merge_av.exe") do (
        echo   文件大小: %%~zA 字节
    )
)

echo.
pause
