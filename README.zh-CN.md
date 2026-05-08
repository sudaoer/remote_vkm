# remote-vkm

[English Version](README.md)

`remote-vkm` 用于将 Windows 主机上的键盘和鼠标事件转发到 Linux 开发板。

- 主机端：由 pixi 管理的 Python 环境，默认打开一个类似虚拟机控制台的捕获窗口。
- 开发板端：基于 C++17/CMake 的接收端，通过 `/dev/uinput` 注入输入事件。
- 传输层：默认使用 `5533` 端口上的纯 TCP。

这个项目面向可信的本地网络环境，不包含认证或加密机制。

## 仓库结构

```text
host/                 Python 主机端的捕获与发送逻辑
board/                Linux 开发板上的 C++ 接收端
pixi.toml             主机端 Python 环境与任务定义
pyproject.toml        Python 包元数据
```

## 构建开发板接收端

在开发板上复制或克隆此仓库后，执行：

```sh
cmake -S board -B board/build
cmake --build board/build
```

如果只想做一个不注入输入事件的网络连通性冒烟测试，可以运行：

```sh
board/build/remote-vkm-receiver --listen 0.0.0.0 --port 5533 --dry-run
```

如果需要真实注入键盘和鼠标事件，可以运行：

```sh
sudo board/build/remote-vkm-receiver --listen 0.0.0.0 --port 5533
```

非 dry-run 模式需要 `/dev/uinput`。如果打开 `/dev/uinput` 失败，先使用 `sudo` 运行；如果要长期使用，建议添加一条 udev 规则，为目标用户授予 `uinput` 访问权限。

## 运行主机端客户端

在 Windows 上，从此仓库安装主机端环境并运行客户端：

```powershell
pixi run host --host <开发板-IP-或主机名> --port 5533
```

常用参数：

```powershell
pixi run host --host <开发板-IP-或主机名> --verbose
pixi run host --host <开发板-IP-或主机名> --capture global
pixi run test
```

`host` 参数是必填项。项目不会默认使用 `k1`，因为当前这台机器无法解析这个 SSH 别名。

## 安全控制

默认主机端模式会打开一个窗口：

- 点击窗口内部即可捕获键盘和鼠标。
- 第一次点击只进入捕获模式，不会发送到开发板。
- 捕获期间鼠标会被隐藏并锁定在窗口内，移动会被回中并作为相对移动发送。
- 按 `Ctrl+Alt` 释放捕获，行为类似虚拟机控制台。
- 关闭窗口或停止控制台进程即可退出。

旧的全局钩子模式仍可通过 `--capture global` 使用。在该模式下，`Ctrl+Alt+P` 用于暂停/恢复事件转发，`Ctrl+Alt+Esc` 用于退出主机端客户端。这些安全热键会在本机被消费，不会继续发送到远端。如果在暂停、释放或退出前，修饰键或鼠标按键已经发往开发板，主机端会先发送对应的释放事件，避免远端输入卡住。

## 协议

每条消息都是一个固定长度为 32 字节的小端序帧：

```text
uint32 magic      "RVKM"
uint8  version    1
uint8  type       0 hello, 1 key, 2 relative move, 3 mouse button, 4 wheel
uint8  action     0 none, 1 press, 2 release
uint8  flags      reserved
uint32 code       Linux evdev key/button code
int32  value1     dx or vertical wheel
int32  value2     dy or horizontal wheel
uint64 sequence
uint32 reserved
```

主机端在连接建立后会立即发送一个 hello 帧。接收端会先校验 magic 和协议版本，再决定是否接受输入事件。

## 部署说明

如果已经可以通过 SSH 连接开发板，一种简单的工作流如下：

```powershell
scp -r board <开发板-IP-或主机名>:/tmp/remote-vkm-board
ssh <开发板-IP-或主机名> "cmake -S /tmp/remote-vkm-board -B /tmp/remote-vkm-board/build && cmake --build /tmp/remote-vkm-board/build"
```

之后在开发板上启动接收端，再在本机运行主机端客户端即可。
