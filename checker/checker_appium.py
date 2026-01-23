#!/usr/bin/env python3
"""
Instagram 詐欺アカウント警告チェッカー (Appium版 - Cloud環境用)
Androidエミュレータ/実機でInstagramアプリを操作し、フォロー時の詐欺警告を検出

Cloud環境向け調整:
- Appium接続先を環境変数化
- ADBパスを環境変数化
- デバイス名を環境変数化
- 進捗コールバック追加
- ファイルパスをDocker環境用に調整
- Oracle Cloud ARM VM (Redroid 12.0.0_64only) で動作確認済み
"""

import csv
import time
import os
import base64
import subprocess
from datetime import datetime
from typing import Callable, Optional
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from dotenv import load_dotenv

load_dotenv()

# 環境変数から設定を読み込み（Cloud環境用デフォルト値）
APPIUM_HOST = os.getenv('APPIUM_HOST', 'appium')
APPIUM_PORT = os.getenv('APPIUM_PORT', '4723')
ADB_PATH = os.getenv('ADB_PATH', 'adb')
DEFAULT_DEVICE_NAME = os.getenv('DEVICE_NAME', 'redroid:5555')

# Cloud環境用ファイルパス
DATA_DIR = os.getenv('DATA_DIR', '/app/data')
SCREENSHOTS_DIR = os.path.join(DATA_DIR, 'screenshots')
RESULTS_DIR = os.path.join(DATA_DIR, 'results')


class InstagramAppiumChecker:
    def __init__(self, username: str, password: str, on_progress: Optional[Callable] = None):
        """
        Args:
            username: Instagramユーザー名
            password: Instagramパスワード
            on_progress: 進捗コールバック関数
                         signature: on_progress(current: int, total: int, username: str, status: str, details: dict)
        """
        self.username = username
        self.password = password
        self.driver = None
        self.results = []
        self.on_progress = on_progress
        self._total_accounts = 0
        self._current_index = 0

    def _report_progress(self, username: str, status: str, details: dict = None):
        """進捗を報告"""
        if self.on_progress:
            try:
                self.on_progress(
                    current=self._current_index,
                    total=self._total_accounts,
                    username=username,
                    status=status,
                    details=details or {}
                )
            except Exception as e:
                print(f"  [進捗報告エラー] {e}")

    def setup_driver(self, device_name: str = None, max_retries: int = 3):
        """Appiumドライバーをセットアップ（リトライ付き）"""
        device_name = device_name or DEFAULT_DEVICE_NAME
        self._device_name = device_name  # リカバリー用に保存

        appium_url = f"http://{APPIUM_HOST}:{APPIUM_PORT}"
        print(f"  Appium接続先: {appium_url}")
        print(f"  デバイス: {device_name}")

        for attempt in range(max_retries):
            try:
                options = UiAutomator2Options()
                options.platform_name = "Android"
                options.device_name = device_name
                options.app_package = "com.instagram.android"
                options.app_activity = "com.instagram.mainactivity.LauncherActivity"
                options.no_reset = True  # アプリデータを保持
                options.auto_grant_permissions = True
                options.new_command_timeout = 600  # タイムアウトを延長

                self.driver = webdriver.Remote(
                    command_executor=appium_url,
                    options=options
                )
                self.driver.implicitly_wait(10)
                print("  Appiumドライバー接続完了")
                return
            except Exception as e:
                print(f"  Appium接続エラー（試行 {attempt + 1}/{max_retries}）: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    raise

    def _is_session_alive(self) -> bool:
        """Appiumセッションが生きているか確認"""
        try:
            self.driver.current_activity
            return True
        except Exception:
            return False

    def _recover_session(self):
        """セッションを復旧"""
        print("  セッション復旧を試行中...")
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
            self.setup_driver(self._device_name)
            print("  セッション復旧完了")
            return True
        except Exception as e:
            print(f"  セッション復旧失敗: {e}")
            return False

    def _restart_session(self):
        """セッションを安全に再起動（メモリ解放）"""
        print("  [バッチ処理] セッション再起動中...")
        try:
            if self.driver:
                self.driver.quit()
                time.sleep(3)
            self.setup_driver(self._device_name)
            self._go_home()
            print("  [バッチ処理] セッション再起動完了")
        except Exception as e:
            print(f"  [バッチ処理] セッション再起動失敗: {e}")
            raise

    def wait_and_find(self, by, value, timeout=10):
        """要素を待機して取得"""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    def wait_and_click(self, by, value, timeout=10):
        """要素を待機してクリック"""
        element = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
        element.click()
        return element

    def is_logged_in(self) -> bool:
        """ログイン済みかチェック"""
        time.sleep(2)
        try:
            page_source = self.driver.page_source
            # Instagramアプリ内にいればログイン済みとみなす
            if "com.instagram.android" in page_source:
                return True
            return False
        except Exception:
            return False

    def login(self) -> bool:
        """Instagramにログイン"""
        try:
            # まずInstagramホーム画面を開く
            self._go_home()

            if self.is_logged_in():
                print("  すでにログイン済み")
                return True

            print("ログイン処理を開始...")

            # ログインボタンをタップ（初回起動時）
            try:
                login_btn = self.wait_and_find(
                    AppiumBy.XPATH,
                    "//android.widget.Button[@content-desc='ログイン' or contains(@text, 'ログイン') or contains(@text, 'Log in')]",
                    timeout=5
                )
                login_btn.click()
                time.sleep(2)
            except TimeoutException:
                pass

            # ユーザー名入力
            username_field = self.wait_and_find(
                AppiumBy.XPATH,
                "//android.widget.EditText[contains(@text, 'ユーザーネーム') or contains(@text, 'Username') or contains(@text, '電話番号')]"
            )
            username_field.clear()
            username_field.send_keys(self.username)
            time.sleep(0.5)

            # パスワード入力
            password_field = self.driver.find_element(
                AppiumBy.XPATH,
                "//android.widget.EditText[contains(@text, 'パスワード') or contains(@text, 'Password')]"
            )
            password_field.clear()
            password_field.send_keys(self.password)
            time.sleep(0.5)

            # ログインボタンをタップ
            self.wait_and_click(
                AppiumBy.XPATH,
                "//android.widget.Button[contains(@text, 'ログイン') or contains(@text, 'Log in')]"
            )

            time.sleep(5)

            # 「情報を保存」などのポップアップをスキップ
            self._dismiss_popups()

            if self.is_logged_in():
                print(f"  ログイン成功: {self.username}")
                return True
            else:
                print("  ログイン失敗")
                return False

        except Exception as e:
            print(f"  ログインエラー: {e}")
            return False

    def _dismiss_popups(self):
        """各種ポップアップを閉じる"""
        popup_buttons = [
            "後で",
            "今はしない",
            "スキップ",
            "Not Now",
            "Skip",
            "OK"
        ]

        for _ in range(3):  # 複数のポップアップに対応
            for btn_text in popup_buttons:
                try:
                    btn = self.driver.find_element(
                        AppiumBy.XPATH,
                        f"//android.widget.Button[contains(@text, '{btn_text}')]"
                    )
                    btn.click()
                    time.sleep(1)
                    break
                except NoSuchElementException:
                    continue

    def open_profile(self, target_username: str) -> str:
        """
        ADB IntentでInstagramプロフィールに直接移動（リトライ付き）

        Returns:
            str: 'success' - 正常にロードできた
                 'not_found' - アカウントが存在しない
                 'load_failed' - ページロード失敗（真っ白など）
                 'error' - その他エラー
        """
        profile_url = f"https://instagram.com/{target_username}"
        print(f"  プロフィールに遷移中: {profile_url}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                subprocess.run([
                    ADB_PATH,
                    'shell', 'am', 'start', '-a', 'android.intent.action.VIEW',
                    '-d', profile_url,
                    '-p', 'com.instagram.android'
                ], check=True)
                time.sleep(2)

                page_source = self.driver.page_source

                # 存在しないアカウントチェック
                if "このページはご利用いただけません" in page_source or "Page Not Found" in page_source or "Sorry, this page isn't available" in page_source:
                    print(f"  アカウントが存在しません: {target_username}")
                    return 'not_found'

                # ページが正常にロードされたかチェック（ユーザー名または基本要素が表示されている）
                if len(page_source) > 1000 and (target_username.lower() in page_source.lower() or 'フォロー' in page_source or 'Follow' in page_source):
                    return 'success'

                # 真っ白（page_sourceが短い）場合はリトライ
                if attempt < max_retries - 1:
                    print(f"  ページロード失敗、リトライ中... ({attempt + 1}/{max_retries})")
                    # ホームに戻してから再試行
                    self._go_home()
                    time.sleep(2)

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  エラー発生、リトライ中... ({attempt + 1}/{max_retries})")
                    time.sleep(3)
                else:
                    print(f"  プロフィール遷移エラー: {e}")
                    return 'error'

        print(f"  プロフィールのロードに失敗（真っ白）: {target_username}")
        return 'load_failed'

    def check_account(self, target_username: str) -> dict:
        """
        対象アカウントをフォローして詐欺警告をチェック（resource-id方式）
        """
        result = {
            'username': target_username,
            'has_warning': False,
            'warning_type': '',
            'warning_details': '',
            'status': 'unknown',
            'timestamp': datetime.now().isoformat(),
            'screenshot': ''
        }

        # 進捗報告: 処理開始
        self._report_progress(target_username, 'checking', {'phase': 'starting'})

        try:
            # URL直アクセスでプロフィールに移動
            profile_result = self.open_profile(target_username)
            if profile_result != 'success':
                result['status'] = profile_result
                self._report_progress(target_username, profile_result, {'phase': 'profile_load'})
                return result

            # ページロード完了を待機（フォローボタンが表示されるまで）
            time.sleep(2)
            for _ in range(10):
                if self._find_follow_button_by_resource_id():
                    break
                time.sleep(0.5)

            # フォロー状態を確認
            if self._is_already_following():
                print(f"  - {target_username}: フォロー中 → 解除して再フォロー")
                # フォロー中ボタンをクリックして解除ダイアログを表示
                self._click_follow_button_for_refollow()
                time.sleep(1)
                # 確認ダイアログでフォロー解除
                try:
                    confirm_btn = self.wait_and_find(
                        AppiumBy.XPATH,
                        "//android.widget.Button[contains(@text, 'フォローをやめる') or contains(@text, 'Unfollow')]",
                        timeout=3
                    )
                    confirm_btn.click()
                    time.sleep(2)
                except TimeoutException:
                    self.driver.back()
                    time.sleep(1)

            # フォローボタンをクリック
            print(f"  - {target_username}: フォローボタンをクリック")
            self._report_progress(target_username, 'checking', {'phase': 'clicking_follow'})

            if not self._find_and_click_follow_button():
                print(f"  フォローボタンが見つからないか、すでにフォロー状態")
                # フォールバック: 座標タップ
                window_size = self.driver.get_window_size()
                self.driver.tap([(window_size['width'] // 2, 580)], 100)

            time.sleep(2)

            # pendingダイアログをチェック・クリア（公開アカウント用）
            self._check_and_dismiss_pending_dialog()

            # 詐欺警告ダイアログをチェック
            warning_detected = self._check_fraud_warning()

            if warning_detected:
                result['has_warning'] = True
                result['warning_type'] = 'fraud_warning'
                result['status'] = 'warning_detected'

                warning_details = self._get_warning_details()
                result['warning_details'] = warning_details

                print(f"  [WARNING] {target_username}: 詐欺警告が検出されました")
                print(f"     詳細: {warning_details}")

                screenshot_path = self._save_screenshot(target_username)
                result['screenshot'] = screenshot_path

                # 進捗報告: 警告検出
                self._report_progress(target_username, 'warning_detected', {
                    'phase': 'completed',
                    'warning_details': warning_details,
                    'screenshot': screenshot_path
                })

                # 警告ダイアログを閉じる
                self._dismiss_warning()

            else:
                result['has_warning'] = False
                result['status'] = 'no_warning'
                print(f"  [OK] {target_username}: 警告なし（正常）")

                # 進捗報告: 警告なし
                self._report_progress(target_username, 'no_warning', {'phase': 'completed'})

                # フォロー解除
                time.sleep(1)
                self._unfollow()

            # 次のアカウント処理前にホームに戻る
            self._go_home()
            return result

        except Exception as e:
            result['status'] = f'error: {str(e)}'
            print(f"  [ERROR] {target_username}: {e}")
            self._report_progress(target_username, 'error', {'phase': 'error', 'error': str(e)})
            self._go_home()
            return result

    def _check_and_dismiss_pending_dialog(self) -> bool:
        """
        'Your request is pending'ダイアログをチェック・閉じる

        Returns:
            bool: pendingダイアログが表示されていた場合True
        """
        pending_patterns = [
            "Your request is pending",
            "Some accounts prefer to manually review followers",
            "リクエストが保留中です",
            "フォローリクエストが送信されました",
        ]

        try:
            page_source = self.driver.page_source
            is_pending = any(pattern in page_source for pattern in pending_patterns)

            if is_pending:
                print(f"    pendingダイアログ検出。OKボタンをタップします")

                # OKボタンを探してクリック
                try:
                    ok_btn = self.driver.find_element(
                        AppiumBy.XPATH,
                        "//android.widget.Button[contains(@text, 'OK')]"
                    )
                    ok_btn.click()
                    time.sleep(1)
                    return True
                except NoSuchElementException:
                    # OKボタンが見つからない場合、上部タップして閉じる
                    size = self.driver.get_window_size()
                    self.driver.tap([(size['width'] // 2, 200)], 100)
                    time.sleep(0.5)
                    return True

            return False
        except Exception as e:
            print(f"    pendingダイアログ処理エラー: {e}")
            return False

    def _check_fraud_warning(self) -> bool:
        """詐欺警告ダイアログが表示されているかチェック"""
        warning_patterns = [
            # 日本語
            "フォローする前にこのア",
            "安全のため",
            "このアカウントについて",
            "利用開始日",
            "アカウント所在地",
            # 英語
            "Review this account before following",
            "Date joined",
            "Account based in",
            "before you follow them",
        ]

        try:
            page_source = self.driver.page_source
            for pattern in warning_patterns:
                if pattern in page_source:
                    return True
            return False
        except Exception:
            return False

    def _get_warning_details(self) -> str:
        """警告ダイアログから詳細情報を取得"""
        details = []

        try:
            # 利用開始日
            try:
                date_elem = self.driver.find_element(
                    AppiumBy.XPATH,
                    "//android.widget.TextView[contains(@text, '利用開始日') or contains(@text, '年')]"
                )
                details.append(f"利用開始日: {date_elem.text}")
            except NoSuchElementException:
                pass

            # アカウント所在地
            try:
                location_elem = self.driver.find_element(
                    AppiumBy.XPATH,
                    "//android.widget.TextView[contains(@text, '所在地') or contains(@text, '国')]"
                )
                details.append(f"所在地: {location_elem.text}")
            except NoSuchElementException:
                pass

        except Exception:
            pass

        return " | ".join(details) if details else "詳細取得失敗"

    def _dismiss_warning(self):
        """警告ダイアログを閉じる（上部タップ）"""
        try:
            # ダイアログ外（上部）をタップして閉じる
            size = self.driver.get_window_size()
            width = size['width']
            self.driver.tap([(width // 2, 200)], 100)
            time.sleep(0.5)
        except Exception:
            pass

    def _unfollow(self):
        """フォロー解除"""
        try:
            # フォロー中/リクエスト済みボタンを探す
            unfollow_btn = self.driver.find_element(
                AppiumBy.XPATH,
                "//android.widget.Button[contains(@text, 'フォロー中') or contains(@text, 'リクエスト済み') or contains(@text, 'Following') or contains(@text, 'Requested')]"
            )
            unfollow_btn.click()
            time.sleep(1)

            # 確認ダイアログでフォロー解除
            confirm_btn = self.driver.find_element(
                AppiumBy.XPATH,
                "//android.widget.Button[contains(@text, 'フォローをやめる') or contains(@text, 'Unfollow')]"
            )
            confirm_btn.click()
            time.sleep(1)
        except NoSuchElementException:
            pass

    def _find_follow_button_by_resource_id(self):
        """resource-idでフォローボタンを検出（最も安定）"""
        resource_ids = [
            "com.instagram.android:id/profile_header_follow_button",
            "com.instagram.android:id/profile_header_user_action_follow_button",
        ]
        for rid in resource_ids:
            try:
                btn = self.driver.find_element(AppiumBy.ID, rid)
                if btn.is_displayed():
                    return btn
            except NoSuchElementException:
                continue
        return None

    def _find_and_click_follow_button(self) -> bool:
        """フォローボタンをクリック（resource-id優先、XPATHフォールバック）"""
        # 方法1: resource-id（最安定）
        btn = self._find_follow_button_by_resource_id()
        if btn:
            text = btn.text or btn.get_attribute("content-desc") or ""
            # フォロー中/リクエスト済みでなければクリック
            if not any(s in text for s in ['Following', 'フォロー中', 'Requested', 'リクエスト済み']):
                btn.click()
                return True
            else:
                print(f"    (すでにフォロー状態: {text})")
                return False

        # 方法2: XPATHフォールバック
        follow_xpaths = [
            "//android.widget.Button[@text='Follow']",
            "//android.widget.Button[@text='フォローする']",
            "//android.widget.Button[contains(@text, 'Follow') and not(contains(@text, 'Following'))]",
        ]
        for xpath in follow_xpaths:
            try:
                btn = self.driver.find_element(AppiumBy.XPATH, xpath)
                if btn.is_displayed():
                    btn.click()
                    return True
            except NoSuchElementException:
                continue

        return False

    def _is_already_following(self) -> bool:
        """resource-idでフォロー状態を確認"""
        btn = self._find_follow_button_by_resource_id()
        if btn:
            text = btn.text or btn.get_attribute("content-desc") or ""
            return any(s in text for s in ['Following', 'フォロー中', 'Requested', 'リクエスト済み'])
        return False

    def _click_follow_button_for_refollow(self):
        """フォロー中/リクエスト済みボタンをクリック（解除ダイアログ表示用）"""
        btn = self._find_follow_button_by_resource_id()
        if btn:
            btn.click()
            return True
        return False

    def _go_home(self):
        """Instagramホーム画面に戻る"""
        try:
            self.driver.start_activity("com.instagram.android", "com.instagram.mainactivity.LauncherActivity")
            time.sleep(2)
        except Exception:
            pass

    def _save_screenshot(self, target_username: str) -> str:
        """スクリーンショットを保存"""
        os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        filename = f"{SCREENSHOTS_DIR}/{target_username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        self.driver.save_screenshot(filename)
        return filename

    def load_accounts_from_csv(self, csv_path: str) -> list:
        """CSVファイルからアカウントリストを読み込む（ヘッダあり/なし両対応）"""
        accounts = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            f.seek(0)

            # ヘッダ行かどうか判定（username, account, userなどのキーワードがあればヘッダ）
            if first_line.lower() in ['username', 'account', 'user'] or ',' in first_line:
                # ヘッダありCSV
                reader = csv.DictReader(f)
                for row in reader:
                    username = row.get('username') or row.get('account') or row.get('user')
                    if username:
                        accounts.append(username.strip().lstrip('@'))
            else:
                # ヘッダなし（1行1アカウント形式）
                for line in f:
                    username = line.strip()
                    if username:
                        accounts.append(username.lstrip('@'))
        return accounts

    def _load_completed_accounts(self, output_path: str, retry_errors: bool = False) -> tuple:
        """
        既存の結果ファイルから完了済みアカウントを読み込む

        Returns:
            tuple: (completed_set, existing_results_list)
        """
        completed = set()
        existing_results = []

        if not os.path.exists(output_path):
            return completed, existing_results

        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    username = row.get('username')
                    status = row.get('status', '')

                    if not username:
                        continue

                    # 正常完了したものはスキップ
                    skip_statuses = ['no_warning', 'warning_detected', 'not_found']
                    if not retry_errors:
                        skip_statuses.extend(['error', 'load_failed'])

                    if any(s in status for s in skip_statuses):
                        completed.add(username)
                        existing_results.append(row)

        except Exception as e:
            print(f"  既存結果読込エラー: {e}")

        return completed, existing_results

    def save_results_to_csv(self, output_path: str):
        """結果をCSVファイルに保存"""
        if not self.results:
            print("保存する結果がありません")
            return

        # 出力先ディレクトリを作成
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else RESULTS_DIR, exist_ok=True)

        fieldnames = ['username', 'has_warning', 'warning_type', 'warning_details', 'status', 'timestamp', 'screenshot']
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for result in self.results:
                writer.writerow(result)
        print(f"\n結果を保存しました: {output_path}")

    def run(self, csv_path: str, output_path: str = None, delay: int = 10, device_name: str = None, batch_size: int = 20, resume: bool = False, retry_errors: bool = False):
        """
        メイン実行関数

        Args:
            csv_path: 対象アカウントのCSVファイルパス
            output_path: 結果出力先（省略時は自動生成）
            delay: アカウント間の待機時間（秒）
            device_name: デバイス名（省略時は環境変数から）
            batch_size: バッチサイズ（この件数ごとにセッション再起動）
            resume: 前回の結果から再開（完了済みをスキップ）
            retry_errors: エラー/ロード失敗のアカウントも再試行
        """
        device_name = device_name or DEFAULT_DEVICE_NAME

        if output_path is None:
            os.makedirs(RESULTS_DIR, exist_ok=True)
            output_path = f"{RESULTS_DIR}/results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        print("=" * 50)
        print("Instagram 詐欺警告チェッカー (Appium版 - Cloud)")
        print("=" * 50)

        # ドライバーセットアップ
        print("\n[1/4] Appium接続中...")
        self.setup_driver(device_name)

        # ログイン確認
        print("\n[2/4] ログイン確認中...")
        if not self.login():
            print("ログインに失敗しました。終了します。")
            self.driver.quit()
            return

        # アカウントリスト読み込み
        print(f"\n[3/4] アカウントリストを読み込み中: {csv_path}")
        accounts = self.load_accounts_from_csv(csv_path)
        print(f"  対象アカウント数: {len(accounts)}")

        # [再開機能] 完了済みアカウントをスキップ
        if resume and output_path:
            completed, existing_results = self._load_completed_accounts(output_path, retry_errors)
            if completed:
                original_count = len(accounts)
                accounts = [a for a in accounts if a not in completed]
                self.results = existing_results  # 既存結果を引き継ぐ
                print(f"  再開モード: {len(completed)}件完了済み、{len(accounts)}件を処理")

        # 進捗追跡用
        self._total_accounts = len(accounts)

        # チェック実行
        print(f"\n[4/4] チェック開始（待機時間: {delay}秒）")
        print("-" * 50)

        for i, account in enumerate(accounts, 1):
            self._current_index = i
            print(f"\n[{i}/{len(accounts)}] チェック中: {account}")

            # 進捗報告: アカウント処理開始
            self._report_progress(account, 'starting', {'phase': 'init'})

            # セッションが切れていたら復旧を試みる
            if not self._is_session_alive():
                print("  セッション切断を検知")
                self._report_progress(account, 'session_recovery', {'phase': 'recovering'})
                if not self._recover_session():
                    print("  セッション復旧失敗。残りをスキップします。")
                    break

            # [バッチ処理] 指定件数ごとにセッション再起動
            if i > 1 and (i - 1) % batch_size == 0:
                print(f"\n  [バッチ処理] {batch_size}件完了。セッション再起動...")
                self._restart_session()

            result = self.check_account(account)
            self.results.append(result)

            # 中間保存（落ちても途中結果が残る）
            if i % 5 == 0:
                self.save_results_to_csv(output_path)
                print(f"  (中間保存完了: {i}件)")

            if i < len(accounts):
                print(f"  {delay}秒待機中...")
                time.sleep(delay)

        # 結果保存
        print("\n" + "=" * 50)
        self.save_results_to_csv(output_path)

        # サマリー表示
        warnings = sum(1 for r in self.results if r['has_warning'])
        normal = sum(1 for r in self.results if r['status'] == 'no_warning')
        not_found = sum(1 for r in self.results if r['status'] == 'not_found')
        load_failed = sum(1 for r in self.results if r['status'] == 'load_failed')
        errors = sum(1 for r in self.results if r['status'] == 'error' or 'error:' in r['status'])

        print(f"\n【結果サマリー】")
        print(f"  警告あり: {warnings}件")
        print(f"  警告なし: {normal}件")
        print(f"  存在しない: {not_found}件")
        print(f"  ロード失敗: {load_failed}件")
        print(f"  エラー: {errors}件")
        print("=" * 50)

        # 進捗報告: 完了
        self._report_progress('', 'completed', {
            'summary': {
                'warnings': warnings,
                'normal': normal,
                'not_found': not_found,
                'load_failed': load_failed,
                'errors': errors
            }
        })

        self.driver.quit()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Instagram 詐欺警告チェッカー (Appium版 - Cloud)')
    parser.add_argument('csv_file', help='対象アカウントのCSVファイル')
    parser.add_argument('-o', '--output', help='結果出力ファイル', default=None)
    parser.add_argument('-d', '--delay', type=int, default=3, help='アカウント間の待機時間（秒）')
    parser.add_argument('--device', default=None, help=f'デバイス名（デフォルト: {DEFAULT_DEVICE_NAME}）')
    parser.add_argument('--batch-size', type=int, default=20, help='バッチサイズ（この件数ごとにセッション再起動）')
    parser.add_argument('--resume', action='store_true', help='前回の結果から再開（完了済みをスキップ）')
    parser.add_argument('--retry-errors', action='store_true', help='エラー/ロード失敗のアカウントも再試行')
    args = parser.parse_args()

    username = os.getenv('INSTAGRAM_USERNAME')
    password = os.getenv('INSTAGRAM_PASSWORD')

    if not username or not password:
        print("エラー: 環境変数 INSTAGRAM_USERNAME と INSTAGRAM_PASSWORD を設定してください")
        return

    checker = InstagramAppiumChecker(username, password)
    checker.run(args.csv_file, args.output, args.delay, args.device, args.batch_size, args.resume, args.retry_errors)


if __name__ == '__main__':
    main()
