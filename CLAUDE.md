# Instagram 詐欺チェッカー Cloud版

## 経緯

### バージョン履歴

1. **local.ver** - 最初のローカル版
   ```
   /Users/fujimakisora/Documents/project-dir/instagram_sagi_checker
   ```

2. **docker.ver** - Docker化版（Apple Siliconで動作せず）
   ```
   /Users/fujimakisora/Documents/project-dir/instagram_sagi_checker_docker
   ```

3. **cloud.ver** - 今回作成（Oracle Cloud向け）
   ```
   /Users/fujimakisora/Documents/project-dir/instagram_sagi_checker_cloud
   ```

### なぜCloud版が必要か

docker.verをApple Silicon Mac + Colimaで動かそうとしたが、**Redroid（Androidエミュレータ）が動作しない**ことが判明。

- 原因: RedroidはLinuxカーネルモジュール（ashmem, binder）が必要
- ColimaのVM環境では提供されない
- 解決策: 各自がクラウドLinux VMにデプロイする方式へ変更

---

## 参照すべきファイル

### local.ver（ロジックの参考）
```
/Users/fujimakisora/Documents/project-dir/instagram_sagi_checker/
```
- Pythonスクリプト、Appiumロジックの元実装

### docker.ver（Docker構成の参考）
```
/Users/fujimakisora/Documents/project-dir/instagram_sagi_checker_docker/
├── docker-compose.yml      # Docker構成（要調整）
├── web/
│   ├── main.py             # FastAPI Web UI
│   ├── Dockerfile
│   └── requirements.txt
├── checker/
│   └── checker_appium.py   # Appiumチェッカーロジック
└── README.md
```

---

## 新しい方針

**各自がOracle Cloudにデプロイする方式**

- 想定ユーザー: 20人程度
- 各自がOracle Cloud Always Free枠を使う
- **永久無料**で運用可能

### Oracle Cloud Always Free スペック
- ARM (Ampere): 4コア / 24GB RAM
- ストレージ: 200GB
- Redroidに十分なスペック

---

## 作るべきもの

1. **Oracle Cloud用セットアップスクリプト** - ワンコマンドで環境構築
2. **デプロイガイド** - 初心者向け手順書（スクショ付き）
3. **docker-compose.yml** - Oracle ARM Linux VM向けに調整（ARM版Redroid使用）

---

## 次のステップ

1. **Oracle CloudでARM VM作成して動作確認** ← 次ここから
2. Redroid ARM版の動作検証
3. セットアップスクリプト作成
4. デプロイガイド作成（スクショ付き）
5. 20人に配布

---

## 進捗ログ

### 2025-01-16
- プロジェクト初期化
- docker.ver / local.ver のコード確認完了
- 作業計画を策定（フェーズ1〜5）
- **次回**: Oracle CloudでARM VM作成（手動作業）
  - ログイン → Compute → Create Instance
  - Shape: VM.Standard.A1.Flex (4 OCPU / 24GB RAM)
  - Image: Ubuntu 22.04
  - Public IP必須
