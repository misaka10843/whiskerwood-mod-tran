# Whiskerwood Mod 翻译

![alt text](.github\assets\image.png)

如果单纯只需要汉化或者配置设置翻译的话可以直接前往releases上下载并双击 `WhiskerwoodModTranslator.exe`

首次启动会创建同目录的 `data\`，保存草稿、目录设置、备份和工具缓存。请将 EXE 放在可写目录，更新时保留 `data\`

Steam 创意工坊目录会自动检测，检测不到时可手动选择UE4SS仅在使用设置汉化时由应用下载

从源码运行时，双击 `启动.cmd`，需要 Python 3.10+ 和 Tkinter。数据目录为`%LOCALAPPDATA%\WhiskerwoodModTranslator`

默认从Windows注册表定位Steam，再读取 `steamapps/libraryfolders.vdf` 查找各盘Steam库

创意工坊优先选择安装了简中文本小修Mod的库

UE4SS游戏目录也按Steam库和游戏安装清单查找，可在项目设置中手动指定目录

1. 导出当前列表 TXT，把文件交给 LLM，要求保留原键和原文，只填写 `translation`。
2. 导入译文 TXT，在「待写入」列表中检查草稿。导入与手工保存的草稿会保留在本机，重启工作台后可继续编辑
3. 点击「写入汉化 Mod」。译文合并到创意工坊项目 `3643964887\zh.txt`，写入前备份到 `%LOCALAPPDATA%\WhiskerwoodModTranslator\backups`。启用该汉化 Mod 后重启游戏查看

「导出 → 已翻译 Mod 清单」生成含名称和 Steam 创意工坊 ID 的 TXT，纳入至少有一条译文的 Mod，包含本地草稿。「分享译文」复制当前筛选中的译文交换文本并打开 GitHub Gist，由用户登录、粘贴并创建分享链接。收件人可以下载 Gist 的 Raw 文本并导入

扫描 PAK 使用 [repak](https://github.com/trumank/repak/releases)

PAK 扫描支持包内英文文本表、可识别的蓝图本地化映射，以及下文所述的模组设置

## 模组设置汉化

对直接在蓝图里注册英文设置的 Mod，使用「项目设置 → UE4SS 设置汉化」。退出游戏后选择「安装并启用」，工具会下载并校验 UE4SS v4.0.0，同时安装设置汉化插件。对于本工具管理的安装，也可停用汉化、重新启用或卸载。卸载会保留外部安装和已修改的文件。

工作台可按「来源 → UE4SS」查看这类设置的名称和说明。编辑后，在游戏退出时使用「写入汉化 Mod」同步到补丁。原始选项 ID、默认值和实际存储的选项值由游戏管理。

## 构建

```powershell
python -m pip install Nuitka==4.3.5 zstandard==0.25.0
.\scripts\build-windows.ps1 -Version v1.0.0
```

输出位于 `build\`。
