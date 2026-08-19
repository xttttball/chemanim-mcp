# ChemAnim

把中文化学动画要求转换为可校验的 Manim 场景：DeepSeek 负责理解需求并给出英文规范名称和候选 isomeric SMILES；程序再查询 PubChem，用 Morgan 指纹比较候选结构，采用数据库结构，并由 RDKit 校验分子式、形式电荷和方程式守恒。Manim 只读取最终 JSON，不执行模型生成的代码。

## 准备

需要 Python 3.12 和 DeepSeek API 密钥。方程式使用 Unicode 化学下标显示，不再依赖 MiKTeX。首次安装：

```powershell
cd C:\Users\i\Documents\chemenv
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

不要把密钥写进源码或 `.env`。在当前 PowerShell 会话中设置：

```powershell
$secureKey = Read-Host "DeepSeek API Key" -AsSecureString
$env:DEEPSEEK_API_KEY = [Net.NetworkCredential]::new("", $secureKey).Password
```

如果要跨新终端保存，请在 Windows 用户环境变量中添加 `DEEPSEEK_API_KEY`，然后重新打开 PowerShell。检查环境：

```powershell
.\check_environment.ps1
```

## 使用

先只生成并检查场景、结构图和核验报告：

```powershell
.\.venv\Scripts\chemanim.exe "演示乙烯与溴的加成反应。生成物为1,2-二溴乙烷，展示所有物质的结构式。" --no-render
```

渲染二维或三维动画：

```powershell
.\.venv\Scripts\chemanim.exe "演示乙烯与溴的加成反应。生成物为1,2-二溴乙烷。" --quality high
.\.venv\Scripts\chemanim.exe "演示乙烯与溴的加成反应。生成物为1,2-二溴乙烷。" --quality high --structure-mode 3d
```

`--structure-mode 3d` 默认自动启用 OpenGL/GPU；二维结构默认使用更兼容的 Cairo。快速预览建议使用 `--quality medium`，需要手动选择时可加 `--renderer opengl` 或 `--renderer cairo`。

二维模式会让同一画面中的结构式共享比例尺，小分子不再被强行放大到与复杂分子相同的宽度。

输出位于：

- `build/scene.json`：最终场景及核验摘要
- `build/verification.json`：PubChem CID、InChIKey、候选/核验 SMILES 和 Morgan Tanimoto 相似度
- `build/molecule_*.svg` 或场景中的 3D 原子/键数据
- `media/`：Manim 视频

流程会在 DeepSeek JSON 无效时最多自动回传修正三次。PubChem 暂时不可用时，会保留候选结构并进行本地 RDKit 校验；未通过校验则停止，不渲染错误结果。

默认使用响应更快的 `deepseek-v4-flash`，化学结构仍由 PubChem 和 RDKit 校验。需要更强规划时可添加 `--model deepseek-v4-pro --request-timeout 180`。

## 更多示例

```powershell
.\.venv\Scripts\chemanim.exe "演示甲苯被氧气选择性氧化为苯甲醛和水，展示全部结构式。" --quality medium
.\.venv\Scripts\chemanim.exe "制作阿莫西林半合成原理动画，保持正确立体化学，不要虚构实验条件。" --no-render
```

## MCP 服务器

项目提供标准 stdio MCP 入口：

```powershell
.\.venv\Scripts\chemanim-mcp.exe
```

MCP 客户端配置示例（密钥由客户端进程继承，不要写进 JSON）：

```json
{
  "mcpServers": {
    "chemanim": {
      "command": "C:\\Users\\i\\Documents\\chemenv\\.venv\\Scripts\\chemanim-mcp.exe"
    }
  }
}
```

服务器暴露 `generate_chemistry_animation` 工具，参数包括 `prompt`、`quality`、`structure_mode`、`render`、`model` 和 `request_timeout`。它只调用受约束的 ChemAnim CLI，不执行模型提交的 Python 代码。
