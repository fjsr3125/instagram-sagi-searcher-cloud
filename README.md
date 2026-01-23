# Instagram 詐欺チェッカー Cloud版

Instagramアカウントの詐欺警告を自動チェックするツールのCloud版です。
Oracle Cloud Always Free（Ubuntu 22.04 ARM）での運用を想定しています。

## 特徴

- **ARM64対応**: Oracle Cloud Always Free（Ubuntu 22.04）で動作
- **Web UI**: ブラウザから簡単操作
- **リアルタイム表示**: Android画面をブラウザで確認可能

## 仕組み

1. Redroid（Androidエミュレータ）でInstagramアプリを動作
2. Appiumで自動操作
3. フォロー時に表示される詐欺警告を検出
4. 結果をCSVでダウンロード

## 必要環境

- Oracle Cloud Always Free ARM（4コア / 24GB RAM）
- Ubuntu 22.04 ARM64
- SSH接続できる環境

## クイックスタート（Oracle Cloud Always Free）

```bash
# 1. リポジトリをクローン
git clone <リポジトリURL>
cd instagram_sagi_checker_cloud

# 2. セットアップ実行（Dockerとbinder設定）
chmod +x setup.sh
./setup.sh

# 3. 再ログイン（dockerグループ反映）
exit && ssh <USER>@<IP>

# 4. 環境変数設定
cp .env.example .env
nano .env  # INSTAGRAM_USERNAME/PASSWORDを設定

# 5. 起動
docker compose up -d
```

## Oracle Cloud Always Free向けの補足手順

### 1) ファイアウォール（UFW）でポートを開放

Web UIとAndroid画面を外部から見れるようにします。

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 6080/tcp
sudo ufw enable
sudo ufw status
```

### 2) 初回起動が遅い場合

Redroidの起動に数分かかることがあります。以下で起動状況を確認してください。

```bash
docker compose logs -f redroid
```

## アクセス先

| サービス | URL |
|----------|-----|
| Web UI | `http://<IP>:8000` |
| Android画面 | `http://<IP>:6080` |

## 詳細ドキュメント

- [デプロイガイド](docs/DEPLOY_GUIDE.md) - 詳細な手順書

## ファイル構成

```
instagram_sagi_checker_cloud/
├── docker-compose.yml   # Docker構成（ARM64対応）
├── setup.sh             # セットアップスクリプト
├── .env.example         # 環境変数テンプレート
├── web/                 # Web UI (FastAPI)
│   ├── main.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── templates/
│   └── static/
├── checker/             # チェッカーロジック
│   └── checker_appium.py
├── data/                # データ保存先
│   ├── uploads/
│   ├── results/
│   └── screenshots/
└── docs/                # ドキュメント
    └── DEPLOY_GUIDE.md
```

## 使い方

1. Web UI (`http://<IP>:8000`) にアクセス
2. CSVファイルをアップロード
3. 「チェック開始」をクリック
4. 完了したら結果CSVをダウンロード

## CSVフォーマット

```csv
username
suspicious_account_1
suspicious_account_2
```

または単純に1行1アカウント：

```
suspicious_account_1
suspicious_account_2
```

## 注意事項

- **テスト用アカウント推奨**: メインアカウントではなくサブアカウントを使用
- **利用規約**: Instagramの利用規約に従って使用してください
- **レート制限**: 短時間に大量のチェックは控えてください

## トラブルシューティング

[デプロイガイド](docs/DEPLOY_GUIDE.md)のトラブルシューティングセクションを参照。

## ライセンス

Private - 個人利用限定
