"""
Instagram詐欺チェッカー Web UI (Cloud版)
FastAPIによるシンプルなWebインターフェース

機能:
- 複数アカウント対応（ローテーション、フォロー上限管理）
- キュー処理（順番待ち、同時実行1つのみ）
"""
import os
import sys
import json
import asyncio
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any
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
DATA_DIR = Path("/app/data")
UPLOAD_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
ACCOUNT_STATS_FILE = DATA_DIR / "account_stats.json"

# ディレクトリが存在しない場合は作成
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ===========================================
# アカウント管理
# ===========================================

# フォロー上限設定
MAX_FOLLOWS_PER_HOUR = 30
MAX_FOLLOWS_PER_DAY = 60


@dataclass
class InstagramAccount:
    """Instagramアカウント情報"""
    username: str
    password: str


@dataclass
class AccountStats:
    """アカウント使用統計"""
    today_follows: int = 0
    last_follow_at: Optional[str] = None
    last_reset_date: Optional[str] = None


def load_instagram_accounts() -> List[InstagramAccount]:
    """
    環境変数からInstagramアカウント情報を読み込む

    優先順位:
    1. INSTAGRAM_ACCOUNTS (JSON配列形式)
    2. INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD (単一アカウント、後方互換)
    """
    accounts = []

    # 複数アカウント形式（推奨）
    accounts_json = os.getenv('INSTAGRAM_ACCOUNTS')
    if accounts_json:
        try:
            accounts_data = json.loads(accounts_json)
            for acc in accounts_data:
                if acc.get('username') and acc.get('password'):
                    accounts.append(InstagramAccount(
                        username=acc['username'],
                        password=acc['password']
                    ))
            if accounts:
                print(f"[アカウント管理] {len(accounts)}個のアカウントを読み込みました")
                return accounts
        except json.JSONDecodeError as e:
            print(f"[アカウント管理] INSTAGRAM_ACCOUNTSのJSON解析エラー: {e}")

    # 単一アカウント形式（後方互換）
    username = os.getenv('INSTAGRAM_USERNAME')
    password = os.getenv('INSTAGRAM_PASSWORD')
    if username and password:
        accounts.append(InstagramAccount(username=username, password=password))
        print(f"[アカウント管理] 単一アカウントモード: {username}")

    return accounts


def load_account_stats() -> Dict[str, AccountStats]:
    """アカウント統計をファイルから読み込む"""
    if not ACCOUNT_STATS_FILE.exists():
        return {}

    try:
        with open(ACCOUNT_STATS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            stats = {}
            for username, stat_data in data.items():
                stats[username] = AccountStats(
                    today_follows=stat_data.get('today_follows', 0),
                    last_follow_at=stat_data.get('last_follow_at'),
                    last_reset_date=stat_data.get('last_reset_date')
                )
            return stats
    except Exception as e:
        print(f"[アカウント管理] 統計読み込みエラー: {e}")
        return {}


def save_account_stats(stats: Dict[str, AccountStats]):
    """アカウント統計をファイルに保存"""
    try:
        data = {}
        for username, stat in stats.items():
            data[username] = {
                'today_follows': stat.today_follows,
                'last_follow_at': stat.last_follow_at,
                'last_reset_date': stat.last_reset_date
            }
        with open(ACCOUNT_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[アカウント管理] 統計保存エラー: {e}")


def reset_daily_stats_if_needed(stats: Dict[str, AccountStats]) -> Dict[str, AccountStats]:
    """日付が変わっていたら統計をリセット"""
    today = date.today().isoformat()
    for username, stat in stats.items():
        if stat.last_reset_date != today:
            stat.today_follows = 0
            stat.last_reset_date = today
    return stats


def get_available_account(accounts: List[InstagramAccount], stats: Dict[str, AccountStats]) -> Optional[InstagramAccount]:
    """
    利用可能なアカウントを取得（60フォロー未満のもの）

    Returns:
        利用可能なアカウント、なければNone
    """
    stats = reset_daily_stats_if_needed(stats)

    for account in accounts:
        stat = stats.get(account.username, AccountStats())
        if stat.today_follows < MAX_FOLLOWS_PER_DAY:
            return account

    return None


def increment_follow_count(stats: Dict[str, AccountStats], username: str) -> Dict[str, AccountStats]:
    """フォロー数をインクリメント"""
    if username not in stats:
        stats[username] = AccountStats(last_reset_date=date.today().isoformat())

    stats[username].today_follows += 1
    stats[username].last_follow_at = datetime.now().isoformat()
    return stats


# グローバルアカウント管理
instagram_accounts: List[InstagramAccount] = []
account_stats: Dict[str, AccountStats] = {}


# ===========================================
# キュー管理
# ===========================================

@dataclass
class QueueItem:
    """キューアイテム"""
    id: str
    filename: str
    submitted_at: str
    status: str = "pending"  # pending / running / completed / failed / cancelled
    progress: int = 0
    total: int = 0
    current_account: Optional[str] = None
    result_file: Optional[str] = None
    error: Optional[str] = None
    instagram_account: Optional[str] = None  # 使用中のInstagramアカウント


# キュー
job_queue: deque[QueueItem] = deque()
current_job: Optional[QueueItem] = None
queue_lock = asyncio.Lock()
queue_worker_running = False

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
# 後方互換性のため残す。キューのcurrent_jobと同期される
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
    "instagram_account": None,  # 使用中のInstagramアカウント
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




def run_checker_sync(csv_path: str, output_path: str, job: Optional[QueueItem] = None):
    """
    チェッカーを同期実行（スレッドプール内で実行される）

    複数アカウント対応:
    - INSTAGRAM_ACCOUNTSから利用可能なアカウントを選択
    - フォロー数を追跡し、上限到達時はアカウント切り替え
    """
    global account_stats, current_job

    # アカウント情報を取得
    if not instagram_accounts:
        add_log("エラー: Instagram認証情報が設定されていません")
        add_log("環境変数 INSTAGRAM_ACCOUNTS または INSTAGRAM_USERNAME/PASSWORD を設定してください")
        execution_state["status"] = "エラー: 認証情報なし"
        execution_state["is_running"] = False
        if job:
            job.status = "failed"
            job.error = "認証情報なし"
        return

    # 利用可能なアカウントを取得
    account_stats = load_account_stats()
    account_stats = reset_daily_stats_if_needed(account_stats)
    current_account = get_available_account(instagram_accounts, account_stats)

    if not current_account:
        add_log("エラー: 全アカウントが本日のフォロー上限に達しています")
        execution_state["status"] = "エラー: 全アカウント上限到達"
        execution_state["is_running"] = False
        if job:
            job.status = "failed"
            job.error = "全アカウント上限到達"
        return

    add_log(f"Instagramアカウント: {current_account.username}")
    execution_state["instagram_account"] = current_account.username
    if job:
        job.instagram_account = current_account.username

    # 進捗コールバックを生成（フォロー数追跡付き）
    def progress_callback_with_stats(current: int, total: int, username: str, status: str, details: dict = None):
        """進捗コールバック（フォロー数追跡付き）"""
        global account_stats, current_job

        # 基本の進捗更新
        execution_state["progress"] = current
        execution_state["total"] = total
        execution_state["current_account"] = username

        if job:
            job.progress = current
            job.total = total
            job.current_account = username

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
            # 警告検出 = フォロー未完了なのでカウントしない
        elif status == 'no_warning':
            add_log(f"[正常] @{username}: 警告なし")
            # 警告なし = 実際にフォロー→解除したのでカウント
            if execution_state.get("instagram_account"):
                account_stats = increment_follow_count(account_stats, execution_state["instagram_account"])
                save_account_stats(account_stats)
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

    try:
        # チェッカーインスタンスを作成
        checker = InstagramAppiumChecker(
            username=current_account.username,
            password=current_account.password,
            on_progress=progress_callback_with_stats
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
        if job:
            job.status = "completed"
            job.result_file = Path(output_path).name

    except Exception as e:
        add_log(f"エラー: チェッカー実行中に例外が発生 - {str(e)}")
        execution_state["status"] = f"エラー: {str(e)}"
        if job:
            job.status = "failed"
            job.error = str(e)

    finally:
        execution_state["is_running"] = False
        execution_state["completed_at"] = datetime.now().isoformat()
        execution_state["current_account"] = None
        execution_state["instagram_account"] = None


async def run_checker(filename: str, job: Optional[QueueItem] = None):
    """
    チェッカーを実行（非同期ラッパー）
    実際の処理は同期関数をスレッドプールで実行
    """
    global current_job

    execution_state["is_running"] = True
    execution_state["current_file"] = filename
    execution_state["status"] = "初期化中"
    execution_state["started_at"] = datetime.now().isoformat()
    execution_state["completed_at"] = None
    execution_state["logs"] = []
    execution_state["progress"] = 0
    execution_state["total"] = 0

    if job:
        job.status = "running"
        current_job = job

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
                if job:
                    job.total = len(accounts)

            add_log(f"対象アカウント数: {len(accounts)}")

            for i, account in enumerate(accounts, 1):
                if not execution_state["is_running"]:
                    add_log("処理が中断されました")
                    if job:
                        job.status = "cancelled"
                    break

                execution_state["progress"] = i
                execution_state["current_account"] = account
                if job:
                    job.progress = i
                    job.current_account = account
                add_log(f"[スタブ] チェック中 ({i}/{len(accounts)}): {account}")
                await asyncio.sleep(1)

            execution_state["status"] = "完了（スタブモード）"
            execution_state["is_running"] = False
            execution_state["completed_at"] = datetime.now().isoformat()
            if job and job.status != "cancelled":
                job.status = "completed"
            add_log("スタブモードでの実行が完了しました")
        except Exception as e:
            add_log(f"エラー: {e}")
            execution_state["status"] = "エラー"
            execution_state["is_running"] = False
            if job:
                job.status = "failed"
                job.error = str(e)
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
            output_path,
            job
        )
    except Exception as e:
        add_log(f"実行エラー: {e}")
        execution_state["status"] = f"エラー: {e}"
        execution_state["is_running"] = False
        execution_state["completed_at"] = datetime.now().isoformat()
        if job:
            job.status = "failed"
            job.error = str(e)
    finally:
        current_job = None


async def process_queue():
    """キューを処理するワーカー"""
    global queue_worker_running, current_job

    if queue_worker_running:
        return

    queue_worker_running = True

    try:
        while job_queue:
            async with queue_lock:
                if not job_queue:
                    break
                job = job_queue.popleft()

            # ジョブを実行
            await run_checker(job.filename, job)

            # 少し待機（連続実行防止）
            await asyncio.sleep(2)
    finally:
        queue_worker_running = False
        current_job = None


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

    # アカウント統計
    stats = load_account_stats()
    stats = reset_daily_stats_if_needed(stats)
    account_info = []
    for acc in instagram_accounts:
        stat = stats.get(acc.username, AccountStats())
        account_info.append({
            "username": acc.username,
            "today_follows": stat.today_follows,
            "remaining": MAX_FOLLOWS_PER_DAY - stat.today_follows,
            "is_available": stat.today_follows < MAX_FOLLOWS_PER_DAY
        })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "results": results,
        "state": execution_state,
        "scrcpy_port": scrcpy_port,
        "accounts": account_info,
        "queue_pending": len(job_queue),
        "current_job": current_job
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
    """チェッカーを開始（キューに追加）"""
    file_path = resolve_safe_csv_path(UPLOAD_DIR, filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    # キューに追加
    job = QueueItem(
        id=str(uuid.uuid4()),
        filename=filename,
        submitted_at=datetime.now().isoformat()
    )

    async with queue_lock:
        job_queue.append(job)

    # キューワーカーを起動（まだ動いていなければ）
    if not queue_worker_running:
        background_tasks.add_task(process_queue)

    # 待ち位置を計算
    queue_position = len(job_queue)
    if current_job:
        queue_position += 1

    return JSONResponse({
        "success": True,
        "message": "キューに追加しました" if queue_position > 1 else "チェックを開始しました",
        "job_id": job.id,
        "queue_position": queue_position
    })


@app.post("/queue")
async def add_to_queue(background_tasks: BackgroundTasks, filename: str):
    """キューに追加（/startのエイリアス）"""
    return await start_checker(background_tasks, filename)


@app.get("/queue")
async def get_queue_status():
    """キュー状況を取得"""
    # 現在のジョブ
    current = None
    if current_job:
        current = {
            "id": current_job.id,
            "filename": current_job.filename,
            "status": current_job.status,
            "progress": current_job.progress,
            "total": current_job.total,
            "current_account": current_job.current_account,
            "instagram_account": current_job.instagram_account,
            "submitted_at": current_job.submitted_at
        }

    # 待ちジョブ
    pending = []
    for job in job_queue:
        pending.append({
            "id": job.id,
            "filename": job.filename,
            "status": job.status,
            "submitted_at": job.submitted_at
        })

    # アカウント統計
    stats = load_account_stats()
    stats = reset_daily_stats_if_needed(stats)
    account_info = []
    for acc in instagram_accounts:
        stat = stats.get(acc.username, AccountStats())
        account_info.append({
            "username": acc.username,
            "today_follows": stat.today_follows,
            "remaining": MAX_FOLLOWS_PER_DAY - stat.today_follows,
            "is_available": stat.today_follows < MAX_FOLLOWS_PER_DAY
        })

    return JSONResponse({
        "current": current,
        "pending": pending,
        "pending_count": len(pending),
        "accounts": account_info
    })


@app.delete("/queue/{job_id}")
async def cancel_queue_job(job_id: str):
    """キューからジョブをキャンセル"""
    async with queue_lock:
        # キュー内を検索
        for i, job in enumerate(job_queue):
            if job.id == job_id:
                job_queue.remove(job)
                return JSONResponse({
                    "success": True,
                    "message": "キューから削除しました"
                })

    # 現在実行中のジョブの場合
    if current_job and current_job.id == job_id:
        execution_state["is_running"] = False
        return JSONResponse({
            "success": True,
            "message": "停止リクエストを送信しました"
        })

    raise HTTPException(status_code=404, detail="ジョブが見つかりません")


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
        "instagram_account": execution_state.get("instagram_account"),
        "queue_pending": len(job_queue),
        "current_job_id": current_job.id if current_job else None,
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


@app.on_event("startup")
async def startup_event():
    """アプリ起動時の初期化"""
    global instagram_accounts, account_stats

    # Instagramアカウント情報を読み込み
    instagram_accounts = load_instagram_accounts()

    if not instagram_accounts:
        print("[警告] Instagramアカウントが設定されていません")
        print("       INSTAGRAM_ACCOUNTS または INSTAGRAM_USERNAME/PASSWORD を設定してください")

    # アカウント統計を読み込み
    account_stats = load_account_stats()
    account_stats = reset_daily_stats_if_needed(account_stats)


# 開発用: ローカル実行時のディレクトリ設定
if __name__ == "__main__":
    import uvicorn

    # ローカル開発用のディレクトリ
    DATA_DIR = BASE_DIR.parent / "data"
    UPLOAD_DIR = DATA_DIR / "uploads"
    RESULTS_DIR = DATA_DIR / "results"
    ACCOUNT_STATS_FILE = DATA_DIR / "account_stats.json"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    uvicorn.run(app, host="0.0.0.0", port=8000)
