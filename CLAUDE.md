# RenderDoc MCP Server

RenderDoc UI拡張機能として動作するMCPサーバー。AIアシスタントがRenderDocのキャプチャデータにアクセスし、DirectX 11/12のグラフィックスデバッグを支援する。

> **対応キャプチャ**: D3D11/D3D12 に加え、WebGPU (D3D12 バックエンド) のキャプチャも
> D3D12 キャプチャとして検査できます。シェーダーソースは Dawn の WGSL→HLSL ローワリング後
> の HLSL です。

## アーキテクチャ

**ハイブリッドプロセス分離方式**:

```
Claude/AI Client (stdio)
        │
        ▼
MCP Server Process (標準Python + FastMCP 2.0)
        │ File-based IPC (%TEMP%/renderdoc_mcp/)
        ▼
RenderDoc Process (Extension + File Polling)
```

## プロジェクト構成

```
RenderDocMCP/
├── mcp_server/                        # MCPサーバー
│   ├── server.py                      # FastMCPエントリーポイント
│   ├── config.py                      # 設定
│   └── bridge/
│       └── client.py                  # ファイルベースIPCクライアント
│
├── renderdoc_extension/               # RenderDoc拡張機能
│   ├── __init__.py                    # register()/unregister()
│   ├── extension.json                 # マニフェスト
│   ├── socket_server.py               # ファイルベースIPCサーバー
│   ├── request_handler.py             # リクエスト処理
│   └── renderdoc_facade.py            # RenderDoc APIラッパー
│
└── scripts/
    └── install_extension.py           # 拡張機能インストール
```

## MCPツール

| ツール名 | 説明 |
|---------|------|
| `list_captures` | 指定ディレクトリ内の.rdcファイル一覧を取得 |
| `open_capture` | キャプチャファイルを開く（既存キャプチャは自動で閉じる） |
| `get_capture_status` | キャプチャ読込状態確認 |
| `get_draw_calls` | ドローコール一覧（階層構造、フィルタリング対応） |
| `get_frame_summary` | フレーム全体の統計情報（ドローコール数、マーカー一覧等） |
| `find_draws_by_shader` | シェーダー名でドローコールを逆引き検索 |
| `find_draws_by_texture` | テクスチャ名でドローコールを逆引き検索 |
| `find_draws_by_resource` | リソースIDでドローコールを逆引き検索 |
| `get_draw_call_details` | 特定ドローコールの詳細 |
| `get_action_timings` | アクションのGPU実行時間を取得 |
| `get_shader_info` | シェーダーソース/定数バッファ |
| `get_buffer_contents` | バッファデータ取得（オフセット/長さ指定可） |
| `get_texture_info` | テクスチャメタデータ |
| `get_texture_data` | テクスチャピクセルデータ取得（mip/slice/3Dスライス対応） |
| `get_pipeline_state` | パイプライン状態全体 |

### get_draw_calls フィルタリングオプション

```python
get_draw_calls(
    include_children=True,      # 子アクションを含める
    marker_filter="Camera.Render",  # このマーカー配下のみ取得
    exclude_markers=["GUI.Repaint", "UIR.DrawChain"],  # 除外するマーカー
    event_id_min=7372,          # event_id範囲の開始
    event_id_max=7600,          # event_id範囲の終了
    only_actions=True,          # マーカーを除外（ドローコールのみ）
    flags_filter=["Drawcall", "Dispatch"],  # 特定フラグのみ
)
```

### キャプチャ管理ツール

```python
# ディレクトリ内のキャプチャファイルを列挙
list_captures(directory="D:\\captures")
# → {"count": 3, "captures": [{"filename": "game.rdc", "path": "...", "size_bytes": 12345, "modified_time": "..."}, ...]}

# キャプチャファイルを開く（既存キャプチャは自動で閉じられる）
open_capture(capture_path="D:\\captures\\game.rdc")
# → {"success": true, "filename": "game.rdc", "api": "D3D11"}
```

### 逆引き検索ツール

```python
# シェーダー名で検索（部分一致）
find_draws_by_shader(shader_name="Toon", stage="pixel")

# テクスチャ名で検索（部分一致）
find_draws_by_texture(texture_name="CharacterSkin")

# リソースIDで検索（完全一致）
find_draws_by_resource(resource_id="ResourceId::12345")
```

### GPU タイミング取得

```python
# 全アクションのタイミングを取得
get_action_timings()
# → {"available": true, "unit": "CounterUnit.Seconds", "timings": [...], "total_duration_ms": 12.5, "count": 150}

# 特定のイベントIDのみ取得
get_action_timings(event_ids=[100, 200, 300])

# マーカーでフィルタリング
get_action_timings(marker_filter="Camera.Render", exclude_markers=["GUI.Repaint"])
```

**注意**: GPUタイミングカウンターはハードウェア/ドライバーによっては利用できない場合があります。
`available: false` が返された場合、そのキャプチャではタイミング情報を取得できません。

## 通信プロトコル

ファイルベースIPC:
- IPCディレクトリ: `%TEMP%/renderdoc_mcp/`
- `request.json`: リクエスト（MCPサーバー → RenderDoc）
- `response.json`: レスポンス（RenderDoc → MCPサーバー）
- `lock`: 書き込み中ロックファイル
- ポーリング間隔: 100ms（RenderDoc側）

## 開発ノート

- RenderDoc内蔵Pythonにはsocket/QtNetworkモジュールがないため、ファイルベースIPCを採用
- RenderDoc拡張機能はPython 3.6標準ライブラリのみ使用
- ReplayControllerへのアクセスは`BlockInvoke`経由で行う

## 参考リンク

- [FastMCP](https://github.com/jlowin/fastmcp)
- [RenderDoc Python API](https://renderdoc.org/docs/python_api/index.html)
- [RenderDoc Extension Registration](https://renderdoc.org/docs/how/how_python_extension.html)
