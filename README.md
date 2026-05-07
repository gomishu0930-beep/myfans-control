# MyFans Affiliate Control Tower

MyFans アフィリエイト管理ツール（Python/FastAPI）

## セットアップ

```bash
pip install -r requirements.txt
python main.py
```

## Replitで動かす

1. GitHubからこのリポジトリをReplitにImport
2. Secretsに `ANTHROPIC_API_KEY` を追加
3. Copy Deskで画像生成を使う場合は、Secretsに `OPENAI_API_KEY` を追加
4. Runを押す

Replitでは `.replit` の設定で `python main.py` が実行されます。ポートはReplit側の `PORT` 環境変数を使い、`0.0.0.0` で公開されます。

## まず使う画面

```text
http://localhost:5000/generator
```

URLを貼るだけで、投稿文・短文版・画像生成AI用プロンプト・動画生成AI用プロンプトをまとめて生成できます。
`ANTHROPIC_API_KEY` を設定するとClaude Opusを優先して使います。モデルは `ANTHROPIC_MODEL` で変更でき、未設定時は `claude-opus-4-7` です。
Anthropic未設定で `OPENAI_API_KEY` がある場合はOpenAIを使い、どちらも未設定の場合は内蔵テンプレートでコピペ用の文面を作ります。

## Affiliate Copy Desk

```text
http://localhost:5000/affiliate-copy-desk
```

取得済みmyfansアフィリエイト200件から、ジャンル検索、作品選択、1行投稿文、添付素材、image2用画像生成をまとめて行う画面です。

画像生成はReplit Secretsの `OPENAI_API_KEY` を使います。設定後に `image2生成` を押すと、生成画像が `/static/affiliate-copy-desk/generated/` に保存され、画面内に表示されます。

任意設定:

```text
OPENAI_IMAGE_MODEL=gpt-image-1.5
OPENAI_IMAGE_SIZE=1024x1024
OPENAI_IMAGE_QUALITY=low
```

`OPENAI_API_KEY` 未設定時は、画面確認用の安全なプレビュー画像にフォールバックします。
