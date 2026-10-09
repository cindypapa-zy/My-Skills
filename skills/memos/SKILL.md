---
name: memos
description: MemOS - AI memory OS for LLM and Agent systems, enabling persistent Skill memory for cross-task skill reuse and evolution. Provides long-term memory, context-aware interactions, and personalization.
allowed-tools: Bash Read Write Exec
metadata:
  {
    "openclaw":
      {
        "emoji": "🧠",
        "homepage": "https://github.com/MemTensor/MemOS",
        "docs": "https://memos-docs.openmem.net/",
      },
  }
---

# MemOS Skill

MemOS (Memory Operating System) is an AI memory system for LLMs and agents that provides:

- **Long-term memory** - Persistent storage across conversations
- **Context-aware interactions** - Personalized responses based on history
- **Knowledge base integration** - Multi-modal memory support
- **Enterprise-grade optimizations** - Built for production use

## Features

- 🎯 +43.70% Accuracy vs. OpenAI Memory
- 🏆 Top-tier long-term memory + personalization
- 🧠 Knowledge base with multi-modal support
- ⚡ High-performance memory retrieval

## Usage

### 基本使用

MemOS 已安装为 Python 包，可以直接导入使用：

```python
import memos

# 查看版本
print(memos.__version__)  # 2.0.6

# 查看可用模块
print([x for x in dir(memos) if not x.startswith('_')])
```

### 记忆立方体 (MemCube)

```python
from memos import GeneralMemCube, GeneralMemCubeConfig
from memos.configs.memory import MemoryConfigFactory

# 创建配置
text_mem_config = MemoryConfigFactory(backend="naive_text")
config = GeneralMemCubeConfig(
    user_id="user_001",
    text_mem=text_mem_config
)

# 创建记忆立方体
cube = GeneralMemCube(config)

# 使用记忆立方体进行记忆管理
# 详细 API 请参考 MemOS 文档
```

### 命令行工具

MemOS 提供 CLI 工具：

```bash
# 查看帮助
python3 -m memos --help

# 其他命令
memos-cli --help
```

## Documentation

- Website: https://memos.openmem.net/
- Docs: https://memos-docs.openmem.net/
- GitHub: https://github.com/MemTensor/MemOS
- Paper: https://arxiv.org/abs/2507.03724

## Version

MemOS 2.0.6 (Stardust)
