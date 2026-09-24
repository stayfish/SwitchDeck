# SwitchDeck

SwitchDeck 的目标是通过 ESP32-S3 触摸屏，在 Windows 和 Mac 之间同时切换显示器输入源与键鼠控制目标。当前阶段只实现 Windows 上的 DDC/CI 验证工具。

## 当前架构

```text
ESP32-S3（后续）
   ↓ BLE / Wi-Fi
Windows 控制程序
   ├─ DDC/CI → Dell U2724D
   └─ 软件 KVM → Windows / Mac（后续）
```

## 环境准备

- Windows 10/11
- Python 3.12 或更高版本
- [uv](https://docs.astral.sh/uv/)
- 显示器 OSD 中启用 DDC/CI

在 PowerShell 中进入项目目录：

```powershell
uv sync
uv run switchdeck list
```

程序默认匹配描述中包含 `U2724D` 的显示器。若系统给出的名称不同，可传入 `--monitor`：

```powershell
uv run switchdeck --monitor DELL list
```

## 找出输入源值

先读取显示器声明的 MCCS capabilities：

```powershell
uv run switchdeck capabilities
```

在输出中查找 `vcp(60(...))`。括号里的值是这台显示器声明支持的输入源值。再读取当前值：

```powershell
uv run switchdeck get
```

保持 Windows 输入时记录当前值，然后手动用显示器 OSD 切到 Mac、再切回 Windows，分别执行 `get`，即可建立端口和值的对应关系。不要仅凭通用 MCCS 表猜测实际端口值。

## 手动切换和回切验证

假设实测 Windows 输入值为 `0x0f`，Mac 输入值为 `0x11`：

```powershell
uv run switchdeck set 0x11
```

关键验证是让同一 Windows 进程保留物理显示器句柄，切到 Mac 后自动尝试切回：

```powershell
uv run switchdeck roundtrip 0x11 0x0f --delay 8
```

如果 8 秒后能自动回到 Windows，说明在非 Windows 输入激活时 DDC/CI 通道仍可用，可以继续开发常驻控制程序。如果不能切回，优先检查：

1. DDC/CI 是否在显示器 OSD 中开启。
2. 显示器的自动输入切换或节能选项是否会断开 Windows 侧通道。
3. 视频线、转接器或扩展坞是否透传 DDC/CI。
4. Windows 与 Mac 的实测输入值是否正确。

紧急情况下可使用显示器实体按键切回，不要在尚未验证回切能力时设置过长延时。

## Windows/macOS 托盘后台程序

完成输入值验证后，启动常驻程序：

```powershell
uv run switchdeck agent
```

默认配置为输入源 A=`0x11`、输入源 B=`0x0F`。运行后：

- 按 `Ctrl+Alt+Space` 在输入源 A 和输入源 B 之间切换。
- 双击系统托盘里的 SwitchDeck 显示器图标进行切换。
- 右键托盘图标可直接选择 `输入源 A` 或 `输入源 B`，也可以退出程序。

如果以后更换接线，可以覆盖输入值：

```powershell
uv run switchdeck agent --input-a 0x0f --input-b 0x11
```

### macOS 准备

Apple Silicon Mac 安装 `m1ddc`：

```bash
brew install m1ddc
```

Intel Mac 安装 `ddcctl`：

```bash
brew install ddcctl
```

然后安装依赖并启动：

```bash
uv sync
uv run switchdeck agent
```

macOS 上快捷键为 `Control+Option+Space`，菜单栏图标可以直接选择 Windows 或 Mac。第一次监听全局快捷键时，需要在“系统设置 → 隐私与安全性 → 辅助功能”中允许当前终端或 SwitchDeck。Apple Silicon 默认调用 `m1ddc`，Intel 默认调用 `ddcctl`。

## 测试

```powershell
uv run python -m unittest discover -s tests -v
```
