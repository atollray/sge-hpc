# 初回設定：Jupyter利用者からSSH未経験者まで

[READMEへ戻る](../README.md) · [困ったとき](troubleshooting.md)

到達点は「手元のPCから、本人のアカウントで非対話SSHを使い、SGEと共有作業場所を確認できること」です。この段階では解析ジョブを投入しません。コマンドの実行場所は、指定がない限り **PCの端末** です。Jupyterのノートブックやサーバー側ターミナルとは区別してください。

## 1. 普段の接続方法と施設情報を確認する

| 普段の方法 | 最初に確認すること |
|---|---|
| ブラウザでJupyterHubへログイン | PCからSSH接続することが許されるか。JupyterのURLやブラウザ認証は、そのままSSH設定には使えない |
| SSHトンネルでJupyterを開く | トンネル用の接続先・鍵・SSH別名を再利用できるか。ただしJupyter用ホストとSGE投入先は異なる場合がある |
| 接続アプリ・起動スクリプトを使う | 設定済みのホスト名・アカウント・認証方式。アプリ独自の鍵形式や設定はOpenSSHへ引き継がれないことがある |
| 分からない | いつもの手順を言葉で説明し、担当者へ確認。トークン付きURL・パスワード・秘密鍵はチャットへ貼らない |

施設の案内や担当者から次を確認します。不明な値を例から推測しないでください。

- SSH接続を許可されたログイン／投入ノード、本人のユーザー名、ポート番号
- 学内ネットワーク・VPN・踏み台の要否
- 許可された認証方式、公開鍵の登録方法、照合用のホスト鍵フィンガープリント
- スケジューラがSGEか、非対話SSHでジョブ操作が許可されるか
- 本人用の共有作業領域、必要ならSGEコマンドのbinディレクトリ

### 既存の接続設定

PCで `ssh <普段の別名>` が既に使えるなら、新しい鍵を作る必要はありません。接続先が今回のSGE投入先であることを確かめ、手順4と5へ進みます。既存の `~/.ssh/config` をAIが確認する場合も、必要なHost設定に絞り、ファイル全体を報告へ転記しません。

## 2. PCのツールを準備する

Windowsはスタートメニューから「PowerShell」または「ターミナル」を開きます。

```powershell
python --version
ssh -V
Get-Command ssh, ssh-keygen, ssh-add
```

Python 3.12以上と、OpenSSHの版・コマンドの場所が表示されれば準備済みです。`python` が見つからず `py -3 --version` が使える場合は、以後の `python` を `py -3` に置き換えます。

Pythonがない場合は[Python公式配布](https://www.python.org/downloads/)または施設指定の方法で導入し、端末を開き直します。OpenSSHがない場合はWindowsの「オプション機能」で **OpenSSHクライアント** を追加します。PCへOpenSSHサーバーを入れる必要はありません。権限がない場合は管理者へ依頼します。[Microsoft公式手順](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse)も参照してください。

macOSは「ターミナル」、Linuxは利用中の端末アプリを開きます。

```bash
python3 --version
ssh -V
command -v ssh ssh-keygen ssh-add
```

不足するものはPython公式配布またはOS・施設指定の方法で導入します。Jupyterサーバー側のPythonの版ではなく、**PCの端末で使うPython** を確認してください。`ssh -V` は通常、版情報を標準エラーへ表示しますが、それだけで失敗とは限りません。

スキルフォルダへ移動できたら `python scripts/sge_hpc.py doctor`（macOS / Linuxは `python3`）でも確認できます。ネットワークや鍵の内容は調べません。

## 3. SSH鍵が必要な場合にだけ用意する

既存の鍵や施設指定の証明書等が使える場合は、その方法を使います。ここは **公開鍵認証が許可され、新しい鍵が必要な人** 向けです。

まず `.ssh` 内のファイル名を確認します。Windowsは `Get-ChildItem "$env:USERPROFILE/.ssh" -Name`、macOS / Linuxは `ls -1 ~/.ssh` です。フォルダがまだない場合のエラーは問題ありません。既存の秘密鍵の内容を開いたり、同名ファイルを上書きしたりしないでください。

以下は専用名 `id_ed25519_hpc` を使う例です。施設がEd25519を認めていることを確認し、同名のファイルがあれば別名を選びます。

Windows：

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE/.ssh" -Force
ssh-keygen -t ed25519 -f "$env:USERPROFILE/.ssh/id_ed25519_hpc"
```

macOS / Linux：

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_hpc
```

パスフレーズを端末で設定します。チャットへ入力する必要はありません。上書きの確認が出たら中止し、保存先を再確認します。

| 作られるファイル | 扱い |
|---|---|
| `id_ed25519_hpc` | 秘密鍵。PCで保管し、送付・公開・チャット添付しない |
| `id_ed25519_hpc.pub` | 公開鍵。施設の登録画面や、指定された担当者へ登録を依頼する際に使う |

公開鍵の表示は、Windowsなら `Get-Content "$env:USERPROFILE/.ssh/id_ed25519_hpc.pub"`、macOS / Linuxなら `cat ~/.ssh/id_ed25519_hpc.pub` です。登録は施設の手順に従います。既存の `authorized_keys` を置き換える操作は行いません。

参考：[OpenSSHの鍵生成](https://man.openbsd.org/ssh-keygen)、[Windowsでの鍵の扱い](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)。

## 4. SSHの別名と初回接続を確認する

PCの `~/.ssh/config` に次の例を **追記・調整** すると、以後 `lab-hpc` で接続できます。Windowsの場所は通常 `%USERPROFILE%\.ssh\config` です。テキストエディターで開き、拡張子 `.txt` を付けずに保存します。既存設定を丸ごと置き換えないでください。

```sshconfig
Host lab-hpc
    HostName hpc.example.org
    User research-user
    Port 22
    IdentityFile ~/.ssh/id_ed25519_hpc
    IdentitiesOnly yes
```

ホスト名とユーザー名は架空の値です。接続先・ユーザー名・ポート・鍵の名前を施設の案内に置き換えます。既存の別名があればそちらを使います。証明書・踏み台等の設定も施設の案内に従ってください。macOS / Linuxでは `chmod 600 ~/.ssh/config` で権限を設定します。

PCの端末から `ssh lab-hpc` で接続します。初回にホスト鍵の確認が出たら、SHA256フィンガープリントを施設が提供する値と照合し、一致してから承認します。不明・不一致なら中止して担当者へ確認してください。ホスト鍵検証を無効化する必要はありません。

ログインできたら、以下の軽い確認だけを行い、PCへ戻ります。

```bash
hostname
id -un
exit
```

表示が意図した投入ノードと本人のアカウントか確認します。Jupyter専用ホストや計算ノードなら、そのまま投入先にせず担当者へ確認します。

## 5. 非対話接続を確認する

ヘルパーは `BatchMode=yes` を使い、パスワード・パスフレーズ・ホスト鍵確認の入力を待ちません。パスフレーズ付き鍵はPCのSSHエージェントへ登録します。

### Windows

通常のPowerShellで `Get-Service ssh-agent` を実行します。停止・無効の場合だけ、PC管理方針を確認し、必要なら管理者権限のPowerShellで次を実行します。権限がない場合は管理者へ依頼します。

```powershell
Set-Service -Name ssh-agent -StartupType Automatic
Start-Service ssh-agent
```

鍵の登録は **普段使う本人の通常のPowerShell** に戻って行います。

```powershell
ssh-add "$env:USERPROFILE/.ssh/id_ed25519_hpc"
ssh-add -l
```

### macOS / Linux

まず既存のエージェントを使います。

```bash
ssh-add ~/.ssh/id_ed25519_hpc
ssh-add -l
```

`Could not open a connection to your authentication agent` と出る場合は、OS・施設のエージェント設定を確認します。必要なら現在の端末で次を実行し、再度鍵を登録します。

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519_hpc
```

この端末のエージェント情報が、既に起動しているWork / Codexへ自動で渡るとは限りません。[AIからだけ接続できない場合](troubleshooting.md)も確認してください。

### 入力なしでの接続試験

PCの端末で実行します。

```text
ssh -o BatchMode=yes -o ConnectTimeout=15 lab-hpc "hostname; id -un"
```

入力を求めず、意図した接続先と本人の名前が出れば合格です。対話接続だけ成功する場合は、鍵の登録・エージェント・認証方式を確認します。MFA等で非対話SSHが認められない場合は、ここで停止して施設へ相談します。MFAを無効化する設定には進みません。

## 6. 個人用設定JSONを作る

`assets/config.example.json` をスキルの **外** にコピーし、例えばホームの `.config/sge-hpc/hpc-config.json` として保存します。保存先のフォルダがなければ作ります。既存設定があれば雛形で上書きせず、内容を確認してください。

以下は記入例です。共有領域も架空の値なので、施設に確認した本人用ディレクトリへ置き換えます。

```json
{
  "target": "lab-hpc",
  "identity_file": "",
  "shared_root": "/shared/research-user/hpc-jobs",
  "sge_bin_dirs": [],
  "exclude": [],
  "max_upload_mb": 100
}
```

| 項目 | 設定 |
|---|---|
| `target` | PCで試験済みのSSH別名、または `ユーザー名@ホスト名` |
| `identity_file` | SSH設定／エージェントを使うなら空文字。必要時だけ本人の鍵の絶対パス（鍵の内容ではない） |
| `shared_root` | 全計算ノードから見える、本人が書き込み可能な既存の作業領域の絶対パス |
| `sge_bin_dirs` | 非対話SSHでSGEが見つからない場合の、リモートbinディレクトリの配列。通常PATHで使えるなら空配列 |
| `exclude` | コード転送から追加で除外する名前／相対パスのglobパターン |
| `max_upload_mb` | 1回のコード転送で許す、非圧縮ファイル合計の上限（MiB）。既定100 |

JSONはUTF-8で保存し、コメントや末尾の余分なカンマを入れません。Windowsのパスは `C:/Users/自分の名前/...` のように `/` で書けます。ポート・踏み台等はSSH設定へ、秘密鍵・パスワードの内容はどちらにも書きません。

`shared_root` は `/home` や `/data` という名前だけで決めず、共有を確認します。作成が必要なら、サーバー上の本人の許可された共有領域内で作ります。PCに同名のフォルダを作っても代わりにはなりません。リモートパスでは `~` や環境変数は展開されません。

## 7. スキルから接続を確認する

スキルフォルダで、PCの端末から実行します。設定を上記の場所へ保存した場合の例です。

Windows：

```powershell
python scripts/sge_hpc.py --config "$env:USERPROFILE/.config/sge-hpc/hpc-config.json" preflight
```

macOS / Linux：

```bash
python3 scripts/sge_hpc.py --config "$HOME/.config/sge-hpc/hpc-config.json" preflight
```

接続先、本人のユーザー名、SGEコマンドと `tar` の確認、共有領域の実体パスが表示されれば合格です。ジョブ投入やリモートのディレクトリ作成は行いません。計算ノードから共有領域が見えることまでは証明しないため、次に[小規模の確認ジョブ](jobs.md)へ進みます。

最後に **AI自身の実行ツールからも同じ `preflight`** を行います。端末で成功しても、AI側のPython・SSH・実行ユーザー・エージェント・ネットワークが異なれば失敗することがあります。失敗した段階とエラーに応じて[トラブル対処](troubleshooting.md)を使います。
