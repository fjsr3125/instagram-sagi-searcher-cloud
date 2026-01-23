"""
Instagram詐欺チェッカー Web UI (Cloud版)
FastAPIによるシンプルなWebインターフェース
"""
import os
import sys
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, Request, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# checkerモジュールをimportパスに追加
sys.path.insert(0, '/app/checker')
try:
    from checker_appium import InstagramAppiumChecker
    CHECKER_AVAILABLE = True
except ImportError:
    CHECKER_AVAILABLE = False
    print("Warning: checker_appium module not found. Running in stub mode.")

# ディレクトリ設定
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path("/app/data/uploads")
RESULTS_DIR = Path("/app/data/results")

# ディレクトリが存在しない場合は作成
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# FastAPIアプリケーション
app = FastAPI(
    title="Instagram詐欺チェッカー",
    description="Instagramアカウントの詐欺可能性をチェックするツール (Cloud版)",
    version="1.1.0"
)

# 静的ファイルとテンプレート設定
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# 実行状態管理（シンプルなインメモリ管理）
execution_state = {
    "is_running": False,
    "current_file": None,
    "progress": 0,
    "total": 0,
    "current_account": None,
    "status": "待機中",
    "logs": [],
    "started_at": None,
    "completed_at": None,
}


def resolve_safe_csv_path(base_dir: Path, filename: str) -> Path:
    """CSVファイル名を安全に解決"""
    if not filename:
        raise HTTPException(status_code=400, detail="ファイル名が不正です")
    safe_name = Path(filename).name
    if safe_name != filename or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="ファイル名が不正です")
    if Path(safe_name).suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="CSVファイルのみ指定可能です")
    base_dir_resolved = base_dir.resolve()
    candidate = (base_dir_resolved / safe_name).resolve()
    if candidate.parent != base_dir_resolved:
        raise HTTPException(status_code=400, detail="ファイル名が不正です")
    return candidate


def add_log(message: str):
    """ログを追加"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    execution_state["logs"].append(f"[{timestamp}] {message}")
    # 最新100件のみ保持
    if len(execution_state["logs"]) > 100:
        execution_state["logs"] = execution_state["logs"][-100:]


# スレッドプール（同期処理を非同期で実行するため）
thread_pool = ThreadPoolExecutor(max_workers=1)


def create_progress_callback():
    """
    進捗コールバック関数を生成
    checker_appium.pyの on_progress 形式に対応
    """
    def on_progress(current: int, total: int, username: str, status: str, details: dict = None):
        """
        進捗コールバック
        Args:
            current: 現在の処理件数
            total: 総件数
            username: 処理中のユーザー名
            status: ステータス (checking, warning_detected, no_warning, error, session_recovery, completed など)
            details: 詳細情報の辞書
        """
        execution_state["progress"] = current
        execution_state["total"] = total
        execution_state["current_account"] = username

        # ステータスに応じてログ追加
        details = details or {}
        phase = details.get('phase', '')

        if status == 'starting':
            add_log(f"処理開始 ({current}/{total}): @{username}")
        elif status == 'checking':
            if phase == 'clicking_follow':
                add_log(f"フォローボタンをクリック: @{username}")
        elif status == 'warning_detected':
            warning_details = details.get('warning_details', '')
            add_log(f"[警告検出] @{username}: {warning_details}")
        elif status == 'no_warning':
            add_log(f"[正常] @{username}: 警告なし")
        elif status == 'not_found':
            add_log(f"[スキップ] @{username}: アカウントが存在しません")
        elif status == 'load_failed':
            add_log(f"[スキップ] @{username}: ページロード失敗")
        elif status == 'error':
            error_msg = details.get('error', 'unknown')
            add_log(f"[エラー] @{username}: {error_msg}")
        elif status == 'session_recovery':
            add_log(f"セッション復旧中...")
        elif status == 'completed':
            summary = details.get('summary', {})
            add_log(f"チェック完了 - 警告あり: {summary.get('warnings', 0)}件, 正常: {summary.get('normal', 0)}件")

    return on_progress


def run_checker_sync(csv_path: str, output_path: str):
    """
    チェッカーを同期実行（スレッドプール内で実行される）
    """
    # 環境変数からInstagramアカウント情報を取得
    ig_username = os.getenv('INSTAGRAM_USERNAME')
    ig_password = os.getenv('INSTAGRAM_PASSWORD')

    if not ig_username or not ig_password:
        add_log("エラー: Instagram認証情報が設定されていません")
        add_log("環境変数 INSTAGRAM_USERNAME と INSTAGRAM_PASSWORD を設定してください")
        execution_state["status"] = "エラー: 認証情報なし"
        execution_state["is_running"] = False
        return

    add_log(f"Instagramアカウント: {ig_username}")

    # 進捗コールバックを生成
    progress_callback = create_progress_callback()

    try:
        # チェッカーインスタンスを作成
        checker = InstagramAppiumChecker(
            username=ig_username,
            password=ig_password,
            on_progress=progress_callback
        )

        # チェック実行
        add_log("Appium接続を開始します...")
        checker.run(
            csv_path=str(csv_path),
            output_path=str(output_path),
            delay=int(os.getenv('CHECK_DELAY', '10')),
            batch_size=int(os.getenv('BATCH_SIZE', '20')),
            resume=True,  # 中断からの再開を有効化
            retry_errors=False
        )

        execution_state["status"] = "完了"
        add_log("全てのチェックが完了しました")

    except Exception as e:
        add_log(f"エラー: チェッカー実行中に例外が発生 - {str(e)}")
        execution_state["status"] = f"エラー: {str(e)}"

    finally:
        execution_state["is_running"] = False
        execution_state["completed_at"] = datetime.now().isoformat()
        execution_state["current_account"] = None


async def run_checker(filename: str):
    """
    チェッカーを実行（非同期ラッパー）
    実際の処理は同期関数をスレッドプールで実行
    """
    execution_state["is_running"] = True
    execution_state["current_file"] = filename
    execution_state["status"] = "初期化中"
    execution_state["started_at"] = datetime.now().isoformat()
    execution_state["completed_at"] = None
    execution_state["logs"] = []
    execution_state["progress"] = 0
    execution_state["total"] = 0

    add_log(f"チェック開始: {filename}")

    csv_path = UPLOAD_DIR / filename

    # 結果出力パス
    result_filename = f"result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path = RESULTS_DIR / result_filename

    # チェッカーが利用可能かチェック
    if not CHECKER_AVAILABLE:
        add_log("エラー: checker_appiumモジュールが利用できません")
        add_log("スタブモードで実行します（実際のチェックは行われません）")

        # スタブモード: CSVファイルを読み込んでダミー結果を生成
        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                accounts = [line.strip() for line in lines[1:] if line.strip()]
                execution_state["total"] = len(accounts)

            add_log(f"対象アカウント数: {len(accounts)}")

            for i, account in enumerate(accounts, 1):
                if not execution_state["is_running"]:
                    add_log("処理が中断されました")
                    break

                execution_state["progress"] = i
                execution_state["current_account"] = account
                add_log(f"[スタブ] チェック中 ({i}/{len(accounts)}): {account}")
                await asyncio.sleep(1)

            execution_state["status"] = "完了（スタブモード）"
            execution_state["is_running"] = False
            execution_state["completed_at"] = datetime.now().isoformat()
            add_log("スタブモードでの実行が完了しました")
        except Exception as e:
            add_log(f"エラー: {e}")
            execution_state["status"] = "エラー"
            execution_state["is_running"] = False
        return

    # 実際のチェッカーを実行（スレッドプールで同期処理を実行）
    execution_state["status"] = "実行中"
    add_log("Instagramチェッカーを起動中...")

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(
            thread_pool,
            run_checker_sync,
            csv_path,
            output_path
        )
    except Exception as e:
        add_log(f"実行エラー: {e}")
        execution_state["status"] = f"エラー: {e}"
        execution_state["is_running"] = False
        execution_state["completed_at"] = datetime.now().isoformat()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """メインページ"""
    # 結果ファイル一覧を取得
    results = []
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
            results.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    # scrcpy-webポートを環境変数から取得
    scrcpy_port = os.getenv('SCRCPY_WEB_PORT', '6080')

    return templates.TemplateResponse("index.html", {
        "request": request,
        "results": results,
        "state": execution_state,
        "scrcpy_port": scrcpy_port
    })


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """CSVファイルをアップロード"""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSVファイルのみアップロード可能です")

    # ファイル名をサニタイズ
    safe_filename = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = UPLOAD_DIR / safe_filename

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        return JSONResponse({
            "success": True,
            "filename": safe_filename,
            "message": "アップロード完了"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"アップロードに失敗しました: {e}")


@app.post("/start")
async def start_checker(background_tasks: BackgroundTasks, filename: str):
    """チェッカーを開始"""
    if execution_state["is_running"]:
        raise HTTPException(status_code=400, detail="既にチェックが実行中です")

    file_path = resolve_safe_csv_path(UPLOAD_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    # バックグラウンドでチェッカーを実行
    background_tasks.add_task(run_checker, filename)

    return JSONResponse({
        "success": True,
        "message": "チェックを開始しました"
    })


@app.post("/stop")
async def stop_checker():
    """チェッカーを停止"""
    if not execution_state["is_running"]:
        raise HTTPException(status_code=400, detail="チェックは実行されていません")

    execution_state["is_running"] = False
    execution_state["status"] = "停止中"

    return JSONResponse({
        "success": True,
        "message": "停止リクエストを送信しました"
    })


@app.get("/status")
async def get_status():
    """実行状況を取得"""
    return JSONResponse({
        "is_running": execution_state["is_running"],
        "current_file": execution_state["current_file"],
        "progress": execution_state["progress"],
        "total": execution_state["total"],
        "current_account": execution_state["current_account"],
        "status": execution_state["status"],
        "logs": execution_state["logs"][-20:],  # 最新20件のログ
        "started_at": execution_state["started_at"],
        "completed_at": execution_state["completed_at"],
    })


@app.get("/results")
async def list_results():
    """結果ファイル一覧を取得"""
    results = []
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
            results.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    return JSONResponse({"results": results})


@app.get("/results/{filename}")
async def download_result(filename: str):
    """結果ファイルをダウンロード"""
    file_path = resolve_safe_csv_path(RESULTS_DIR, filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="text/csv"
    )


@app.get("/uploads")
async def list_uploads():
    """アップロード済みファイル一覧を取得"""
    uploads = []
    if UPLOAD_DIR.exists():
        for f in sorted(UPLOAD_DIR.glob("*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
            uploads.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    return JSONResponse({"uploads": uploads})


# 開発用: ローカル実行時のディレクトリ設定
if __name__ == "__main__":
    import uvicorn

    # ローカル開発用のディレクトリ
    UPLOAD_DIR = BASE_DIR.parent / "data" / "uploads"
    RESULTS_DIR = BASE_DIR.parent / "data" / "results"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    uvicorn.run(app, host="0.0.0.0", port=8000)
