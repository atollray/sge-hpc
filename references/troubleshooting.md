# 困ったとき

[READMEへ戻る](../README.md) · [初回設定](setup.md) · [ジョブ実行](jobs.md)

「PCの準備 → 対話SSH → 非対話SSH → preflight → SGEジョブ」のうち、最初に失敗した段階から確認します。後の操作を繰り返しても、前段の問題は解決しません。

## PC・SSH

| 症状・表示例 | 確認と次の操作 |
|---|---|
| `python` / `python3` が見つからない、版が3.12未満 | PC側のPythonを導入・更新。Windowsでは `py -3 --version` も確認し、利用できれば `python` を `py -3` に置換 |
| `ssh` / `ssh-keygen` / `ssh-add` が見つからない | OpenSSHクライアントを導入。PCでSSHサーバーを起動する必要はない |
| `Could not resolve hostname` | ホスト名・SSH別名・DNS・VPNを確認。JupyterのURLを入力していないか、SSH設定が `config.txt` になっていないか確認 |
| `Connection timed out` / `No route to host` | 学内ネットワーク・VPN・接続先・ポート・踏み台を施設の案内と照合 |
| `Connection refused` | 指定ホスト／ポートでSSHを受け付けているか担当者へ確認 |
| 初回に `Are you sure you want to continue connecting` | 施設が提供するホスト鍵のフィンガープリントと照合してから承認 |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | 接続を止め、ホスト変更の有無と新しいフィンガープリントを担当者へ確認。確認前にknown_hostsを削除しない |
| `Permission denied (publickey...)` | 本人のユーザー名、公開鍵の登録、SSH設定の鍵の場所、`ssh-add -l` を確認。パスワード認証等だけが許可される環境では施設へ相談 |
| 対話SSHは成功、`BatchMode=yes` は失敗 | 未登録のホスト鍵、未読込のパスフレーズ付き鍵、MFA／入力必須の認証を確認。認証要求を迂回せず、施設の認める方法を使う |
| `Could not open a connection to your authentication agent` | OSのSSHエージェントを確認。[初回設定](setup.md)の手順5を参照 |
| `Bad permissions` / `UNPROTECTED PRIVATE KEY FILE` | ファイル所有者・権限を確認。Unixでは本人の秘密鍵を `chmod 600`、`.ssh` を `chmod 700`。Windowsは本人・管理者によるACL確認を行い、Everyoneへ権限を広げない |

### PCの端末では成功するが、AIからは失敗する

AIの実行環境で `doctor` を行い、次をPCの端末と比べます。

1. 同じPC・同じ利用者の環境か。クラウド側で実行していないか。
2. 同じPythonとOpenSSHを使っているか。Windows標準SSH、Git付属SSH、WSLでは設定・エージェントが異なることがある。
3. 同じSSH設定と鍵のパスが見えているか。macOS / Linuxではエージェントの環境変数を継承しているか。
4. ツールの実行権限やネットワーク制限がないか。

必要なエージェント環境を継承できる起動方法を確認するか、PCの端末でコマンドを実行します。単に再起動すれば直るとは限りません。AIへ秘密鍵をアップロードして解決しようとしないでください。

## 設定・SGE・ファイル転送

| 症状・表示例 | 確認と次の操作 |
|---|---|
| `Set target ...` | 雛形の `target` が空。PCで確認済みのSSH別名等を記入 |
| JSONの読込エラー | UTF-8、半角の引用符、余分なカンマやコメントを確認。Windowsパスは `/` を使える |
| `SSH identity file not found` | `identity_file` はPC側の鍵のパス。SSH設定で指定済みなら空文字にできる |
| `MISSING: qsub` 等 | 本当にSGE投入先へ接続しているか確認。通常のSSHログインと非対話SSHでPATHが異なることがある。必要なら `sge_bin_dirs` を設定 |
| `qsub` は見つかるが `SGE_ROOT` 等の設定が不足 | binへのPATH追加だけでは不十分。施設指定の非対話シェルのSGE環境を整える |
| `Shared root ...` のエラー | リモートの共有ディレクトリが存在し、本人に書込・移動権限があるか確認。PC側のパスではない |
| `--remote must be below shared_root` | 実行先を共有作業領域の下の新しい実行フォルダへ指定。共有領域そのものは指定しない |
| `Path escapes shared_root` | 実行先のシンボリックリンクが別領域を指していないか確認 |
| `Configure the job template first` | 雛形の末尾を実処理へ置換し、`CONFIGURE_BEFORE_SUBMIT` マーカーを削除 |
| `Job script must use LF line endings` | エディターでジョブファイルの改行をLFにして保存 |
| `exceeds max_upload_mb` | dry-runで対象を確認し、不要物を除外。大きな入力はサーバーに置く。必要量が分かってから上限を調整 |
| `qw` | 通常は資源待ち。要求した資源やキュー設定、施設の混雑状況を確認 |
| `Eqw` / エラー状態 | `status` の詳細と `qstat -j`、出力先や作業場所を確認。共有領域、`logs/`、資源指定が典型的な確認点。自動で再投入しない |
| キューにないが `qacct` 記録がない | 会計情報の反映遅延や施設の記録設定を確認し、今回のログも確認。成功とは断定しない |
| qsub後に通信断／応答解析エラー | 投入済みの可能性がある。`qstat` とログ等を確認してから再実行を判断 |
| 回収時に `tar` が失敗／パスがない | リモートの実行先と `logs` / `results` の有無、権限、ジョブ状態を確認。あるものだけ回収するなら `--allow-missing` |
| `Result archive contains links ...` | 最終成果を通常ファイルとして別の結果フォルダへまとめ、その相対パスを `--paths` に指定 |

## 相談時に伝えること

担当者には、OS、失敗段階、実行したコマンドとエラー、SGEならジョブ番号・投入時刻を伝えます。公開Issueやチャットでは内部ホスト名・ユーザー名・パスを架空の値へ置換し、秘密鍵、パスワード、Jupyterトークンを含めません。`ssh -v` 等の詳細ログにも内部情報が出るため、全文をそのまま公開しないでください。

参考：[OpenSSHのBatchMode](https://man.openbsd.org/ssh_config#BatchMode)、[WindowsのSSH鍵・エージェント](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement)。
