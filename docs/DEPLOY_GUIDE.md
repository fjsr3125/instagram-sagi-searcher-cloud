# Instagram 詐欺チェッカー Cloud版 - デプロイガイド（Oracle Cloud Always Free）

Oracle Cloud Always Free（Ubuntu 22.04 ARM）でのデプロイ手順です。

## 前提条件

- Oracle Cloud Always Free ARM（4コア / 24GB RAM）
- Ubuntu 22.04 ARM64
- SSHクライアント（ターミナル、PuTTY等）
- SSH鍵ペア（既存のものを使用、または新規作成）

---

## Step 1: Oracle CloudでARM VMを作成

1. Oracle Cloudの管理画面にログイン
2. ARM VMを作成
3. OSは **Ubuntu 22.04 (ARM64)** を選択
4. 公開IPが付与されていることを確認

---

## Step 2: SSHで接続

```bash
# SSH接続
ssh ubuntu@<PUBLIC_IP>
```

初回接続時は `yes` と入力してフィンガープリントを承認します。

---

## Step 3: リポジトリ取得とセットアップ

```bash
# ホームディレクトリで実行
cd ~

git clone <リポジトリURL> instagram_sagi_checker_cloud
cd instagram_sagi_checker_cloud

# セットアップ
chmod +x setup.sh
./setup.sh
```

セットアップ完了後に **再ログイン** してください。

```bash
exit
ssh ubuntu@<PUBLIC_IP>
```

---

## Step 4: 環境変数の設定

```bash
cp .env.example .env
nano .env
```

`INSTAGRAM_USERNAME` と `INSTAGRAM_PASSWORD` を設定します。

---

## Step 5: 起動

```bash
docker compose up -d
```

---

## Step 6: ファイアウォール（UFW）設定

Web UIとAndroid画面を外部から見れるようにします。

```bash
sudo ufw allow 8000/tcp
sudo ufw allow 6080/tcp
sudo ufw enable
sudo ufw status
```

---

## アクセス先

| サービス | URL |
|----------|-----|
| Web UI | `http://<PUBLIC_IP>:8000` |
| Android画面 | `http://<PUBLIC_IP>:6080` |

---

## 起動確認

起動状況は以下で確認できます。

```bash
docker compose ps
```

Redroidの起動に時間がかかる場合は以下を確認してください。

```bash
docker compose logs -f redroid
```
