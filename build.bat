@echo off
rem ============================================================
rem  merge_av 一键构建脚本 (PyInstaller)
rem
rem  用法:
rem    build.bat              双击运行 / 命令行运行（结束后暂停）
rem    build.bat nopause      构建结束后不暂停（供 VS Code 任务等调用）
rem
rem  产物: dist\merge_av.exe
rem ============================================================
setlocal
chcp 65001 >nul

set "NOPAUSE="
if /i "%~1"=="nopause" set "NOPAUSE=1"

cd /d "%~dp0"

echo ============================================================
echo   merge_av 构建脚本
echo ============================================================
echo   工作目录: %CD%
echo.

rem ---------- 1. 选择 Python 解释器（优先虚拟环境） ----------
set "PY="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        set "PY=.venv\Scripts\python.exe"
        echo [1/5] 使用虚拟环境: .venv
    ) else (
        echo [1/5] 警告: .venv 解释器不可用（基础 Python 可能已被移动或删除）
        echo        如需重建虚拟环境，请执行: python -m venv --clear .venv
    )
)
if not defined PY (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [错误] 未找到可用的 Python，请先安装 Python 3.7+ 并加入系统 PATH。
        if not defined NOPAUSE pause
        exit /b 1
    )
    set "PY=python"
    echo [1/5] 回退使用全局 Python
    for /f "delims=" %%p in ('python -c "import sys;print(sys.executable)" 2^>nul') do echo         %%p
)

rem ---------- 2. 检查必需文件 ----------
echo [2/5] 检查源文件与 spec...
if not exist "merge_av.py" (
    echo [错误] 未找到 merge_av.py
    if not defined NOPAUSE pause
    exit /b 1
)
if not exist "merge_av.spec" (
    echo [错误] 未找到 merge_av.spec
    if not defined NOPAUSE pause
    exit /b 1
)
echo        merge_av.py / merge_av.spec 就绪

rem ---------- 3. 安装/升级 PyInstaller ----------
echo [3/5] 检查 PyInstaller...
"%PY%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo        未安装，正在安装 PyInstaller...
    "%PY%" -m pip install --upgrade pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败，请手动执行: pip install pyinstaller
        if not defined NOPAUSE pause
        exit /b 1
    )
) else (
    echo        已安装
)

rem ---------- 4. 检查可选依赖 InquirerPy ----------
echo [4/5] 检查 InquirerPy（可选，提供交互式菜单）...
"%PY%" -c "import InquirerPy" >nul 2>nul
if errorlevel 1 (
    echo        未安装，正在安装 InquirerPy...
    "%PY%" -m pip install --upgrade inquirerpy
    if errorlevel 1 (
        echo        警告: InquirerPy 安装失败，将降级为键盘序号输入模式
    )
) else (
    echo        已安装
)

rem ---------- 5. 清理并构建 ----------
echo [5/5] 开始构建 (pyinstaller merge_av.spec --clean --noconfirm)...
echo.
"%PY%" -m PyInstaller merge_av.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo [错误] 构建失败，请查看上方日志。
    if not defined NOPAUSE pause
    exit /b 1
)

if not exist "dist\merge_av.exe" (
    echo.
    echo [错误] 构建过程未报错，但未生成 dist\merge_av.exe。
    if not defined NOPAUSE pause
    exit /b 1
)

echo.
echo ============================================================
echo   构建成功！
echo   产物: %CD%\dist\merge_av.exe
echo.
echo   提示: 使用 exe 仍需系统已安装 ffmpeg 并加入 PATH。
echo ============================================================
if not defined NOPAUSE pause
exit /b 0
