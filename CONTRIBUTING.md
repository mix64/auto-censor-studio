# 開発

## 開発環境

Python 3.12以降で仮想環境を作り、開発用の依存を含めてインストールします。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## ソースの構成

```text
auto_censor_studio/
  core/        # Qtに依存しない範囲の形、モザイク、PNGの入出力、作業ファイル
  services/    # モデルの推論とQThreadのジョブ
  ui/          # 編集キャンバス、画面、一括処理、テーマ
  assets/      # アイコン、フォント、同梱ライセンス
  models.py    # モデルのファイル名、取得URL、SHA-256
  paths.py     # ユーザーデータの保存先
  __main__.py  # アプリの起動
tests/         # 単体、GUI、一括処理の回帰テスト
tools/         # アイコンとexeの生成スクリプト
```

`services/` はUIのウィジェットを直接変更しません。
バックグラウンド処理の結果は、`ui/` がメインスレッドで画面に反映します。

モデルの取得元とハッシュは `models.py` だけで管理しています。
モデルを差し替えるときは、ここと [THIRD_PARTY.md](THIRD_PARTY.md) の両方を更新してください。

アプリアイコンは `auto_censor_studio/assets/app-icon.svg` を編集し、`python tools/build_icon.py` でPNGとICOを生成し直します。

配布用の exe は `python tools/build_exe.py` で `dist/AutoCensorStudio/` に生成します。
ソースを変えたら exe を作り直さないと反映されません。
`auto_censor_studio/assets/` の中身は exe に同梱するので、アセットを追加したときも作り直してください。

## 検証

CIは用意していないので、変更したら次のコマンドをローカルで実行してください。

```powershell
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m build
```

回帰テストは合成画像だけを使うので、モデルをダウンロードしなくても実行できます。
実際のモデルで推論が通るかは、モデルを準備したあとに `python tests/model_smoke.py` で確かめます。
どちらのテストも、実際のイラストに対する検出精度を測るものではありません。

処理結果、確認済みの状態、元画像を保護する挙動のいずれかを変えるときは、対応する回帰テストも更新してください。
テストには合成画像を使い、個人のイラストをコミットしないでください。

## コミットする前に

`git status --short --untracked-files=all` で、意図しないファイルが含まれていないかを確認してください。
`.gitignore` は仮想環境、モデル、設定、既定の名前で保存した作業ファイルと出力画像を除外します。
任意の名前で置いた画像までは除外できません。

モデルはリポジトリに含めず、セットアップ時に固定したリビジョンから取得します。
MIT Licenseが適用されるのはアプリ独自のソースだけです。
モデルやフォントを再配布するときは、それぞれの出所とライセンスを確認してください。
