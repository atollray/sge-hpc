# ジョブの準備・投入・結果回収

[READMEへ戻る](../README.md) · [初回設定](setup.md) · [困ったとき](troubleshooting.md)

PCで `preflight` が成功した状態から始めます。以下の操作はPCから行い、SGEが解析を計算ノードへ割り当てます。接続確認だけの依頼ではここへ進みません。

## 最初は小規模の確認ジョブ

スキルの外に、確認専用のフォルダを作ります。`new-job --local <フォルダ>` で、そこへ `job.sge` を作ります（既存ファイルは上書きしません）。設定JSONに `job_template` があればその雛形、無ければ `assets/job.sge` がコピーされます。施設の設定を確認して編集し、編集後はUTF-8・改行LFで保存します。

| 編集する場所 | 確認事項 |
|---|---|
| `#$ -pe smp 4` | 並列環境名とスロット数。`smp` は施設依存。1スロットで `-pe` が不要な施設では行を除く |
| `#$ -l mem_req=4G` | メモリ資源名・値・スロット当たりかどうか。小規模確認に合う値へ調整 |
| キュー指定 | 指定が必要な施設だけ `#$ -q <施設のキュー名>` を追加 |
| 環境設定 | 本解析に必要なConda・modules等。今回の軽い確認なら追加不要 |
| 末尾の停止部分 | `# CONFIGURE_BEFORE_SUBMIT`、説明用 `echo`、`exit 2` を下記の確認処理へ置換 |

```bash
{
    printf 'host='; hostname
    printf 'user='; id -un
    printf 'cwd='; pwd -P
    printf 'job_id=%s\n' "${JOB_ID:-unknown}"
    printf 'slots=%s\n' "${NSLOTS:-1}"
} > results/check.txt
```

これはホスト名等を結果へ書くだけの処理です。PCとクラスタ間の転送、SGE投入、計算ノードからの共有領域への読み書き、結果回収を一通り確認します。資源指定は施設の案内を優先してください。

## 計画を表示する

スキルフォルダにいる状態で、変数を本人の値へ置き換えます。例のフォルダ名・共有パスは架空です。実行ごとに新しいリモートフォルダを選びます。`--remote` は設定の `shared_root` より下の絶対パスにします。

Windows（PowerShell）：

```powershell
$hpcConfig = "$env:USERPROFILE/.config/sge-hpc/hpc-config.json"
$hpcLocal = "$env:USERPROFILE/hpc-check"
$hpcRemote = '/shared/research-user/hpc-jobs/check-001'
python scripts/sge_hpc.py --config "$hpcConfig" submit --local "$hpcLocal" --remote "$hpcRemote" --job job.sge --dry-run
```

macOS / Linux：

```bash
hpc_config="$HOME/.config/sge-hpc/hpc-config.json"
hpc_local="$HOME/hpc-check"
hpc_remote='/shared/research-user/hpc-jobs/check-001'
python3 scripts/sge_hpc.py --config "$hpc_config" submit --local "$hpc_local" --remote "$hpc_remote" --job job.sge --dry-run
```

WindowsのGit Bashから実行すると、`/` で始まるリモートパスがWindowsのパスに書き換えられます。Git Bashではコマンドの前に `MSYS_NO_PATHCONV=1` を付けるか、PowerShellを使ってください。

dry-runでは、SSH接続・転送・ジョブ投入を行わず、ローカルで対象とジョブ内容を表示します。接続先、入力ファイル、コマンド、資源指定、出力先を確認します。**共有された端末ログやチャットにも計画内容が出る**ため、ジョブに秘密情報を直接書かないでください。

## 許可を得て投入する

具体的な計画について投入の許可を得てから、同じ端末・同じ変数を使い、`--dry-run` を `--approved` に置き換えます。CLIを本人が直接使う場合は、本人が計画を確認して実行することが投入の意思表示です。

Windows：

```powershell
python scripts/sge_hpc.py --config "$hpcConfig" submit --local "$hpcLocal" --remote "$hpcRemote" --job job.sge --approved
```

macOS / Linux：

```bash
python3 scripts/sge_hpc.py --config "$hpc_config" submit --local "$hpc_local" --remote "$hpc_remote" --job job.sge --approved
```

転送後に `logs/` を作成し、`qsub -terse` で投入します。表示された `JOBID`、投入時刻、作業場所を控えます。通信断や応答解析エラーで投入成否が不明なら、`qstat` を確認してから判断します。再実行による重複投入を避けてください。

## 状況確認と回収

以下の `12345` は実際の番号へ置き換えます。

Windows：

```powershell
python scripts/sge_hpc.py --config "$hpcConfig" status 12345
python scripts/sge_hpc.py --config "$hpcConfig" collect --remote "$hpcRemote" --local "$env:USERPROFILE/hpc-output/check-001" --paths logs results --dry-run
python scripts/sge_hpc.py --config "$hpcConfig" collect --remote "$hpcRemote" --local "$env:USERPROFILE/hpc-output/check-001" --paths logs results
```

macOS / Linux：

```bash
python3 scripts/sge_hpc.py --config "$hpc_config" status 12345
python3 scripts/sge_hpc.py --config "$hpc_config" collect --remote "$hpc_remote" --local "$HOME/hpc-output/check-001" --paths logs results --dry-run
python3 scripts/sge_hpc.py --config "$hpc_config" collect --remote "$hpc_remote" --local "$HOME/hpc-output/check-001" --paths logs results
```

短いジョブは `watch` で終わるまで待てます。30秒ごとに確認し、キューから消えたら `status` と同じ記録を表示します。エラー状態（`Eqw` 等）になったら理由を表示して止まり、既定の300秒を過ぎたら「まだ実行中」と表示して止まります。どちらの場合もジョブは取り消しません。`--interval` と `--timeout` で秒数を変えられ、`--timeout 0` は無制限です。AIの実行ツールには1回の実行時間の上限があるため、それより短くします。

Windows：

```powershell
python scripts/sge_hpc.py --config "$hpcConfig" watch 12345 --timeout 300
```

macOS / Linux：

```bash
python3 scripts/sge_hpc.py --config "$hpc_config" watch 12345 --timeout 300
```

ジョブがキューから消えた後、`status` は `qacct` の主要項目（所有者・時刻・終了状態・実行時間・最大メモリ等）を表示します。全項目は `status 12345 --full` で見られます。今回の `qacct` 記録と `logs/` を照合します。ジョブ番号は再利用されるため、`qacct` が同じ番号の他人の過去記録を返すことがあります。`status` はそれを除き、本人の記録が無ければ「本人の記録なし」と表示します。本人の過去のジョブが同じ番号で残ることもあるので、投入時刻とジョブ名も確認します。回収した `results/check.txt` が期待どおりなら、一連の確認は完了です。

本解析では、確認処理を目的のプログラムに置き換え、必要な資源と環境を調整します。大量の一時ファイルは施設が提供する `$TMPDIR` 等を使い、最終成果を共有領域の `results/` へ戻します。

## プロジェクトと実行フォルダの分け方

何度も使う大きな入力と、実行ごとの作業場所を分けます。

```text
<共有領域>/<プロジェクト>/                    大きな入力・参照DB・解析環境など、何度も使うもの
<共有領域>/<プロジェクト>/runs/<日時-名前>/     実行ごとのコード・job.sge・logs/・results/
```

- `--remote` には実行フォルダを指定します。`20261109-1530-blast-v2` のように日時と内容が分かる名前にすると、どのコードからどの結果が出たかを後から辿れます。
- ジョブから大きな入力を読むときは、プロジェクトのフォルダを絶対パスで書きます（例：`PROJ=/shared/research-user/hpc-jobs/myproj` と置き、`"$PROJ/data/..."` で参照）。`../../data` のような相対パスは、フォルダの深さが変わると壊れます。
- 大きな入力はこのスキルで転送せず、施設の案内に従ってサーバー上に置きます。
- これまで1つのフォルダを使い回してきた場合は、そのフォルダをプロジェクトのフォルダとして残し、新しい実行だけを `runs/` の下に作れます。入力を移す必要はありません。

## 転送・上書きの範囲

- 転送は追加と同名ファイルの上書きです。転送先の余分なファイルを削除しません。毎回別の実行フォルダを使います（[分け方](#プロジェクトと実行フォルダの分け方)）。
- 既定で `.git`、`.ssh`、`.env` 系、代表的な鍵名、キャッシュ、`data/`、`logs/`、`results/` 等を除外します。全ての秘密ファイルを自動検出するわけではありません。
- 小さな入力は `input/` に置けます。大きな入力はサーバーに置き、ジョブから共有パスで参照します。合計100 MiB超は既定で転送前に停止します。
- `--exclude '<パターン>'` または設定の `exclude` で除外を追加できます。シンボリックリンクはアップロードしません。
- `sync` は転送だけを行います。`--dry-run` も使えます。転送だけでSGEジョブは投入されません。
- 回収は指定パスが全て取得できた場合に展開します。ジョブが失敗して `results/` が無いときなど、存在するものだけ回収するには `--allow-missing` を付けます。無かったパスは表示されます。既存の同名ローカルファイルは上書きします。回収対象のシンボリックリンクや特殊ファイルは拒否するため、必要なら通常ファイルの最終成果を別フォルダにまとめます。
- `submit` は `logs/` と、ジョブファイルの `#$ -o` / `#$ -e` に書いた相対パスのフォルダ（`-cwd` のジョブのみ）を投入前に作ります。dry-runの `Created before qsub` で確認できます。絶対パスや `$` を含む出力先は `Not created` と表示されるので、自分で作ります。ジョブ内で作ってもSGEが先に開くため間に合いません。
