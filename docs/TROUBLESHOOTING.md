# Troubleshooting

## WSL2 NTFS 마운트에서 uv sync 실패 (Operation not permitted)

**현상**: WSL2에서 Windows 드라이브(`/mnt/d/` 등)에 있는 프로젝트 폴더로 `uv sync` 실행 시 패키지 설치 실패

**오류 메시지**:

```
error: Failed to install: ipykernel-7.2.0-py3-none-any.whl (ipykernel==7.2.0)
  Caused by: Failed to copy to `/mnt/d/.../inprocess/.tmpVKxJt7/blocking.py`
  Caused by: failed to copy file ... : Operation not permitted (os error 1)
```

### 원인

uv는 파일 설치 시 임시 파일(`.tmpXXXXXX`)을 생성한 뒤 atomic rename하는 방식을 사용한다.
WSL2가 NTFS를 9P 드라이버로 마운트한 경로(`/mnt/c/`, `/mnt/d/` 등)에서는 이 오퍼레이션이 허용되지 않아 `EPERM (Operation not permitted)` 발생. `sudo`로 실행해도 파일시스템 레벨의 제약이므로 동일하게 실패한다.

### 해결 방법

두 가지 방법 중 선택:

**방법 1 — 프로젝트를 Linux 파일시스템으로 이동 (권장)**

프로젝트 폴더를 WSL 네이티브 경로(`~/`)로 옮기거나 새로 clone.

```bash
cd ~
git clone <remote-url> robotics_manipulation
cd robotics_manipulation
uv sync --group teleop
```

WSL 파일시스템은 성능과 심링크·권한 호환성 모두 우수하다.

**방법 2 — Windows 마운트에 Linux 메타데이터 활성화**

`/mnt/` 경로를 그대로 유지해야 한다면 WSL 마운트 옵션에 메타데이터를 추가한다.

```ini
# /etc/wsl.conf
[automount]
options = "metadata,umask=22,fmask=11"
```

저장 후 Windows PowerShell에서 WSL 재시작:

```powershell
wsl --shutdown
```

이후 WSL을 다시 열고 `uv sync` 재실행.

### 확인 방법

```bash
python -c "import lerobot, torch; print('lerobot', lerobot.__version__, '/ torch', torch.__version__)"
```

## 카메라 대역폭 제한

**현상**: `lerobot-find-cameras` 실행 시 카메라가 탐지는 되지만 일부만 캡처에 성공함

**오류 메시지**:

```
Failed to connect or configure OpenCV camera 1: Failed to open OpenCVCamera(1)
Failed to connect or configure OpenCV camera 2: Failed to open OpenCVCamera(2)
```

**카메라 모델**: Microdia Integrated_Webcam_HD — USB 2.0 전용(추정)

**지원 해상도 프로파일**: `1280×720`, `640×480` 두 가지만 존재 (그 외 해상도 설정 불가)

### 원인

탐지 단계(`find_cameras`)에서는 카메라를 1대씩 열고 즉시 닫으므로 전체가 보이지만,
연결·스트리밍을 동시에 유지하면 일부 카메라가 열리지 않는다.

USB 2.0 카메라 1대의 YUY2 전송량:

```
640 × 480 × 2 bytes × 30 fps = 18.4 MB/s
```

### 테스트 결과

| 구성 | 결과 |
|------|------|
| USB 허브 + YUY2 | 1대만 성공 |
| USB 허브 + MJPEG | 1대만 성공 |
| PC 포트 직접 연결 (각각) | 2대 이상 성공 ✅ |

USB 허브 자체의 하드웨어 한계로, MJPEG로 전송량을 줄여도 허브에서는 동시에 1대만 스트리밍된다.
USB 3.2 허브도 내부적으로 USB 2.0 카메라는 HS 경로(480 Mbps 공유)를 사용하므로 허브 교체로는 해결되지 않는다.

### 해결 방법

**카메라마다 PC USB 포트에 직접 연결** (유일하게 확인된 해결책)

현재 PC(ThinkStation) 기준 사용 가능한 포트:
```
전면: 4× USB 3.2 Gen 1
후면: 4× USB 3.2 Gen 1
     2× USB 2.0
```

카메라 3대를 허브 없이 전부 직접 꽂을 수 있다.


### USB 버전 확인 방법

카메라의 USB 버전 확인

```powershell
# 1. 카메라 InstanceId 조회 (Status OK인 항목 확인)
Get-PnpDevice -Class Camera | Select-Object Status, InstanceId

# 2. ACPI 경로에서 포트 접두사 확인 (<InstanceId>에 위 결과 붙여넣기)
(Get-PnpDeviceProperty -InstanceId "USB\VID_0C45&PID_64AB&MI_00\<InstanceId>" |
  Where-Object { $_.KeyName -eq "DEVPKEY_Device_LocationPaths" }).Data |
  Where-Object { $_ -match "ACPI" }
```

출력 예시:

```markdown
ACPI(_SB_)#ACPI(PC00)#ACPI(XHCI)#ACPI(RHUB)#ACPI(HS09)#USB(2)#USBMI(0)
                                              ^^^^^^^^^^
                                              여기를 본다
```

| 접두사 | USB 버전 | 최대 속도 |
|--------|---------|---------|
| `HS##` | USB 2.0 | 480 Mbps |
| `SS##` | USB 3.0 | 5 Gbps |
| `SSP##` | USB 3.1/3.2 | 10+ Gbps |

USB 허브 버전 확인

```powershell
Get-WmiObject -Class Win32_USBHub | Select-Object DeviceID, Name
```

| 장치 이름 | USB 버전 |
|-----------|---------|
| `Generic USB Hub` | USB 2.0 |
| `Generic SuperSpeed USB Hub` | USB 3.0 |


## Docker 컨테이너에서 Vulkan 초기화 실패 (Linux)

**현상**: `docker compose up` 으로 컨테이너를 띄우면 Isaac Sim 이 다음 에러를 토하면서 GPU 가속을 잃고 software 로 fallback 된다. CUDA 자체는 동작하지만 (nvidia-smi 에서 컨테이너 안의 python 프로세스가 GPU 메모리를 점유) 렌더링·카메라·GPU PhysX 가 모두 죽는다.

**오류 메시지**:

```log
[Error] [carb.graphics-vulkan.plugin] VkResult: ERROR_INCOMPATIBLE_DRIVER
[Error] [carb.graphics-vulkan.plugin] vkCreateInstance failed.
                Vulkan 1.1 is not supported, or your driver requires an update.
[Error] [omni.gpu_foundation_factory.plugin] Failed to create any GPU devices,
                including an attempt with compatibility mode.
[Error] [omni.physx.plugin] CUDA libs are present, but no suitable CUDA GPU was found!
[Warning] [omni.physx.plugin] PhysX warning: GPU solver pipeline failed,
                switching to software
```

### 원인

호스트의 NVIDIA 드라이버가 `.run` 인스톨러로 **`--no-opengl-files`** 옵션과 함께 설치된 경우, `libGLX_nvidia.so.0` / `libnvidia-glcore.so.<ver>` / `libEGL_nvidia.so.0` 같은 그래픽스 유저 스페이스 라이브러리가 호스트에 통째로 빠져 있다. 이 상태에서는 다음이 모두 성립한다:

1. `/etc/vulkan/icd.d/nvidia_icd.json` 은 존재하지만 `library_path: libGLX_nvidia.so.0` 이 가리키는 실제 파일이 호스트에 없다 (dangling pointer).
2. `nvidia-container-cli list` 출력에 `GLX_nvidia` / `glcore` / `EGL_nvidia` 가 한 줄도 없다 → nvidia-container-runtime 이 컨테이너로 마운트할 라이브러리 자체가 호스트에 없다.
3. 컨테이너 안에서 `NVIDIA_DRIVER_CAPABILITIES=all` 을 줘도 마운트할 게 없으니 Vulkan ICD 가 동작 못 한다.

기존 설치 옵션은 `/var/log/nvidia-installer.log` 에서 확인할 수 있다:

```bash
head -15 /var/log/nvidia-installer.log
# nvidia-installer command line:
#     ./nvidia-installer
#     --no-kernel-module
#     --no-opengl-files       ← 이게 원인
#     --silent
```

추가로, docker-compose 의 `deploy.resources.reservations.devices` (`capabilities: [gpu]`) 방식은 `nvidia-container-toolkit ≥ 1.19` 의 일부 환경에서 graphics capability 를 트리거하지 않는다. 같은 호스트에서 legacy 방식 (`runtime: nvidia` + `NVIDIA_VISIBLE_DEVICES=all`) 으로 띄우면 Vulkan ICD JSON 은 마운트되지만, 위 1번 이유로 라이브러리 자체가 없어서 결국 동일하게 실패한다.

### 해결 방법

같은 버전의 `.run` 인스톨러를 다시 받아서 **커널 모듈은 건드리지 않고 그래픽스 유저 스페이스만** 추가 설치한다.

```bash
# 1. 기존 컨테이너 정지 + GPU 사용 프로세스 종료 확인
docker compose down
nvidia-smi

# 2. 동일 버전 .run 다운로드 (Data Center / Tesla 경로에 호스팅됨)
cd /tmp
DRIVER_VER=$(cat /proc/driver/nvidia/version | awk '/NVRM/ {print $8}')
curl -fLO "https://us.download.nvidia.com/tesla/${DRIVER_VER}/NVIDIA-Linux-x86_64-${DRIVER_VER}.run"
chmod +x "NVIDIA-Linux-x86_64-${DRIVER_VER}.run"

# 3. --no-opengl-files 빼고 --install-libglvnd 추가, 커널 모듈은 그대로 둠
sudo sh "./NVIDIA-Linux-x86_64-${DRIVER_VER}.run" \
    --no-kernel-module \
    --install-libglvnd \
    --silent
```

`--no-kernel-module` 가 핵심이다. 커널 모듈은 이미 동작 중이므로 건드리지 않고, 빠져 있던 GL/Vulkan/EGL 유저 스페이스 라이브러리만 채워 넣는다.

또한 `docker-compose.yaml` 의 GPU 접근 방식은 legacy syntax 로 두는 편이 안정적이다:

```yaml
services:
  leisaac-debug:
    runtime: nvidia
    network_mode: host          # livestream WebRTC 동적 포트 협상에 유리
    environment:
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: all
    volumes:
      - /etc/vulkan/icd.d:/etc/vulkan/icd.d:ro   # ICD JSON 안전망
    # deploy: 블록은 사용하지 않음 (graphics capability 트리거 불안정)
```

### 확인 방법

설치 후 호스트에서:

```bash
ls /usr/lib/x86_64-linux-gnu/libGLX_nvidia.so.0
ls /usr/lib/x86_64-linux-gnu/libnvidia-glcore.so.${DRIVER_VER}
ls /usr/lib/x86_64-linux-gnu/libEGL_nvidia.so.0
nvidia-container-cli list | grep -E 'GLX_nvidia|glcore|EGL_nvidia'
```

세 파일이 모두 존재하고 `nvidia-container-cli list` 에 GLX/glcore/EGL 항목이 출력되면 호스트 측 준비 완료.

컨테이너 안에서:

```bash
docker compose run --rm leisaac-debug bash -c '
  ldconfig -p | grep -E "libGLX_nvidia|libvulkan|libnvidia-glcore" &&
  apt-get install -y vulkan-tools && vulkaninfo --summary
'
```

`vulkaninfo --summary` 가 NVIDIA GPU 의 `deviceName` 과 `apiVersion 1.4.x` 를 출력하면 컨테이너 안에서도 Vulkan 이 정상이다. 이후 `docker compose up` 시 위의 `ERROR_INCOMPATIBLE_DRIVER` / `Failed to create any GPU devices` / `no suitable CUDA GPU was found` / `switching to software` 메시지가 모두 사라진다.

#### Headless 서버에서 외부 PC 로 화면 송출

호스트에 디스플레이가 없는 경우 (서버 환경) Isaac Sim 은 `--headless --livestream=2` (사내망 WebRTC) 로 띄워 외부 PC 에서 Omniverse Streaming Client / 호환 WebRTC 클라이언트로 접속한다. 이때 컨테이너가 바인드하는 포트는 다음과 같다:

| 포트 | 프로토콜 | 용도 | 출처 |
|------|---------|------|------|
| 8011 | TCP | HTTP signaling | `omni.services.transport.server.http` |
| 48010 | TCP | livestream core | `omni.kit.livestream.core` |
| 49100 | TCP | WebRTC media | `omni.kit.livestream.webrtc` |
| 47998-48020 | UDP | 동적 미디어 범위 | `omni.services.livestream.nvcf` |

`network_mode: host` 면 별도 포트 매핑 없이 그대로 노출된다. WebRTC 동적 미디어 협상이 NAT 뒤에서 깨지는 경우가 있어 host network 가 가장 안정적이다.

## `lerobot record` 키보드 컨트롤이 동작하지 않음 (WSLg + Windows Terminal)

**현상**: `docker compose ... run --rm lerobot record` 실행 후 우측/좌측 화살표·Esc 를 눌러도 에피소드 시작/정지·재녹화·종료가 트리거되지 않는다. 증상은 두 단계로 나타난다.

**증상 ①** — DISPLAY 와 `/tmp/.X11-unix` 가 컨테이너에 노출되지 않은 경우, pynput import 자체가 실패하며 다음 트레이스 + `Switching to headless mode` 가 출력된다.

```
ImportError: this platform is not supported:
('failed to acquire X connection: Bad display name ""', DisplayNameError(''))
```

**증상 ②** — DISPLAY/X11 소켓을 노출시켜 pynput 이 정상 import 된 뒤에도 키 입력이 묵묵부답. 콘솔에는 raw escape sequence (`^[[C` 등) 만 찍힌다.

### 원인

①: `lerobot/utils/control_utils.py` 의 `is_headless()` 는 `import pynput` 성공 여부로 헤드리스 환경을 판별한다. 컨테이너에 `DISPLAY` 가 없거나 `/tmp/.X11-unix` 가 마운트되지 않으면 import 가 실패 → `is_headless()` 가 `True` → `init_keyboard_listener()` 가 `None` 리스너를 반환.

②: WSLg 의 X 서버는 X11 윈도우로부터 들어온 키 이벤트만 본다. **Windows Terminal 은 X11 클라이언트가 아니라 Windows 네이티브 콘솔**이라, 거기서 누른 키는 X 서버를 거치지 않고 Windows 와 그 자식 (WSL → docker → 컨테이너 PTY) 으로만 흘러간다. pynput 의 X RECORD 리스너는 X 서버 측 이벤트만 듣기 때문에 이 키들을 영원히 보지 못한다.

### 해결 방법

두 단계로 나눠 적용한다.

**① docker-compose 에 X11 노출** (`docker/docker-compose.yaml`, `lerobot` 서비스):

```yaml
    volumes:
      ...
      # X11 소켓 — pynput import 시 X 연결 실패를 막기 위해 마운트
      - /tmp/.X11-unix:/tmp/.X11-unix
    environment:
      NVIDIA_VISIBLE_DEVICES:     all
      NVIDIA_DRIVER_CAPABILITIES: compute,utility,video
      DISPLAY: ${DISPLAY:-:0}
```

이것만으로는 ② 가 해결되지 않으니 동시에:

**② 컨테이너 안에 stdin 기반 키보드 리스너 패치 베이크 인** (`docker/Dockerfile.lerobot`):

```dockerfile
COPY docker/lerobot_keyboard_stdin.py /opt/venv/lib/python3.11/site-packages/lerobot_keyboard_stdin.py
COPY docker/lerobot_keyboard_stdin.pth /opt/venv/lib/python3.11/site-packages/lerobot_keyboard_stdin.pth
```

패치 모듈은 `/dev/tty` 를 cbreak 모드로 열어 docker PTY 로 흘러온 raw escape sequence (`\x1b[C`/`\x1b[D`/`\x1b`) 를 읽어 lerobot 이 기대하는 `{exit_early, rerecord_episode, stop_recording}` 이벤트 딕셔너리를 그대로 토글한다. `.pth` 파일이 Python 시작 시 `install_hook()` 을 호출, `lerobot.utils.control_utils` 가 import 되는 순간 `init_keyboard_listener` 를 stdin 버전으로 교체한다.

패치 적용 후 이미지를 재빌드해야 한다.

```bash
docker compose -f docker/docker-compose.yaml build lerobot
```

### 확인 방법

```bash
# 1. 패치 모듈이 이미지에 들어갔는지 확인
docker compose -f docker/docker-compose.yaml run --rm --no-deps --entrypoint python lerobot \
  -c "import lerobot.utils.control_utils as cu, lerobot_keyboard_stdin; \
      print(cu.init_keyboard_listener is lerobot_keyboard_stdin.init_keyboard_listener_stdin)"
# → True

# 2. record 실행 → 첫 에피소드 진행 중 우측 화살표 →
#    'Right arrow key pressed. Exiting loop...' 가 콘솔에 출력
docker compose --env-file .env -f docker/docker-compose.yaml run --rm lerobot record
```

stdin 패치가 X 의존성을 완전히 우회하므로 WSLg 가 아닌 헤드리스 Linux 서버 (디스플레이 없음) 에서도 동일하게 동작한다. ① 의 docker-compose X11 노출은 pynput import 자체가 시작 시 트레이스를 뱉지 않게 하는 안전망 역할만 한다 (없어도 패치는 동작하지만 헤드리스 폴백 메시지가 한 번 찍힘).

## 카메라 sensor 가 raytracing pipeline 생성 실패 (RT 코어 없는 GPU)

> ⚠ **H100/A100은 Isaac Sim 5.1 공식 미지원이다.** NVIDIA 공식 [System Requirements](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)가 다음과 같이 명시:
> > *"GPUs without RT Cores (A100, H100) are not supported."*
>
> 즉 H100/A100은 시스템 요구사항 단계부터 제외되어 있고, 아래 증상은 그 결과물이다. 워크어라운드를 찾기보다 GPU를 교체하는 게 정답.

**현상**: 위 Vulkan 문제를 해결한 뒤 (`Driver Version: ... | Graphics API: Vulkan` 가 정상 출력되고 `Streaming server started.` 까지 도달) 그 직후, 환경 초기화 단계에서 다음 트레이스로 컨테이너가 즉시 종료된다.

**오류 메시지**:

```log
[Error] [carb.graphics-vulkan.plugin] VkResult: ERROR_INITIALIZATION_FAILED
[Error] [carb.graphics-vulkan.plugin] vkCreateRayTracingPipelinesKHR failed.
[Error] [omni.physx.fabric.plugin] CUDA error: an illegal memory access was encountered:
                                   .../DirectGpuHelper.cpp: 563

Traceback (most recent call last):
  File ".../teleop_se3_agent.py", line 226, in main
    env = gym.make(task_name, cfg=env_cfg).unwrapped
  File ".../isaaclab/envs/mdp/observations.py", line 404, in image
    images = sensor.data.output[data_type]
  File ".../isaaclab/sensors/sensor_base.py", line 362, in _update_outdated_buffers
    self._is_outdated[outdated_env_ids] = False
RuntimeError: CUDA error: an illegal memory access was encountered
```

### 원인

NVIDIA가 시스템 요구사항 문서에서 H100/A100을 미지원으로 명시한 이유와 정확히 일치하는 메커니즘이다. 데이터센터 GPU인 **NVIDIA H100 / A100 (Hopper / Ampere-DC)** 은 **RT 코어를 탑재하지 않는다**. RT 코어는 RTX A/L 워크스테이션 시리즈와 GeForce RTX, 그리고 일부 데이터센터 GPU (L40 / L40S / A40 / RTX 6000 Ada) 에만 있다.

Isaac Sim 5.1 의 카메라 sensor (`isaaclab.sensors.camera.Camera` / `TiledCamera`) 는 무조건 RTX renderer (`RaytracedLighting` / `PathTracing`) 로 동작하도록 강제되어 있다 (`isaaclab/sensors/camera/camera_cfg.py:64`, `isaaclab/apps/isaaclab.python.rendering.kit:50-71` 에 raytracing 비활성화 옵션 부재). 그래서 RT 코어 없는 GPU 에서는 다음 흐름으로 죽는다:

1. `--enable_cameras` 로 카메라 sensor 등록
2. RTX renderer 가 `vkCreateRayTracingPipelinesKHR` 호출 → `ERROR_INITIALIZATION_FAILED`
3. `omni.physx.fabric` 가 비어 있는/유효하지 않은 GPU 버퍼를 참조 → CUDA illegal memory access
4. observation manager 가 `sensor.data.output[...]` 접근 → 이미 corrupt 된 CUDA context 라 `RuntimeError`

CUDA 자체는 정상이고 (`nvidia-smi` 에서 컨테이너의 python 프로세스가 GPU 메모리 점유), GPU 가 두 장 모두 인식되며 livestream 서버까지 정상 기동한 뒤 발생하기 때문에 위쪽 Vulkan 섹션의 증상과는 구분된다.

GPU 별 RT 코어 유무 빠른 가이드 (NVIDIA 공식 시스템 요구사항 기준):

| GPU | 아키텍처 | RT 코어 | Isaac Sim 5.1 지원 |
|------|---------|---------|------|
| H100 / H200 | Hopper | ✗ | **NVIDIA 공식 미지원** (문서 명시) |
| A100 | Ampere-DC | ✗ | **NVIDIA 공식 미지원** (문서 명시) |
| L40 / L40S / L4 | Ada-DC | ✓ | 동작 |
| A40 / A30 | Ampere-DC (visualization) | ✓ | 동작 |
| RTX A4000 / A5000 / A6000 | Ampere | ✓ | 동작 (RT 코어·16GB VRAM 충족) |
| RTX 6000 Ada / 5000 Ada | Ada | ✓ | 동작 |
| GeForce RTX 4080 (최소) / 5080 (양호) / PRO 6000 Blackwell (이상적) | 컨슈머·Pro | ✓ | NVIDIA **권장** |
| GeForce RTX 30 시리즈 | Ampere | ✓ | 권장 라인업 미만이지만 RT 코어·16GB(3080 12GB는 미달) 충족 시 동작 |


## 시뮬레이션 기동 시 무시해도 되는 로그

`teleop_se3_agent.py` 가 정상 기동한 상태에서도 수십~수백 줄의 `[Error]` / `[Warning]` 로그가 찍힌다. 대부분 **LeIsaac 제공 scene USD 에셋 자체의 품질 이슈**에서 유래하며, 시뮬레이션·텔레오퍼레이션 기능에는 영향이 없다.

기동 성공 판단 기준: 로그 하단에 다음이 출력되면 정상 동작 상태다.

```
SO101-Leader connected.
 Running calibration of SO101-Leader
...
+-------------------------------------------------+
|  Teleoperation Controls for so101_leader        |
|   B  | start control                            |
|   R  | reset simulation ...                     |
|   N  | reset simulation ...                     |
+-------------------------------------------------+
```

### 로그 카테고리별 해석

| 로그 패턴 | 의미 | 대응 |
|---------|------|------|
| `[Error] [omni.physx.plugin] PhysicsUSD: Parse collision - triangle mesh collision (approximation None/MeshSimplification) cannot be a part of a dynamic body, falling back to convexHull approximation` | 씬 속 가구(cabinet/drawer/handle 등) 의 collision geometry 가 dynamic body 에 쓸 수 없는 triangle mesh 로 authored 됨 → PhysX 가 자동으로 convex hull 근사로 대체 | 물리 근사 품질이 약간 떨어질 뿐. 무시 |
| `[Error] [omni.physx.plugin] PhysX error: Supplied PxGeometry is not valid. Shape creation method returns NULL.`<br>`PhysX Shape failed to be created on a prim: .../outlet_room/...`, `.../light_switch_room/...` | 씬 속 콘센트·전등스위치 prim 의 geometry 가 유효하지 않아 shape 생성 실패 | 단순 장식 요소 한정. pick-and-place 와 무관, 무시 |
| `[Error] [omni.physx.plugin] PhysicsUSD: CreateJoint - cannot create a joint between static bodies, joint prim: .../wall_*/world_fixed_joint` | 벽·바닥 등 static body 쌍 사이에 fixed joint 를 만들려다 실패 | static 끼리는 조인트가 불필요, 무시 |
| `[Warning] [omni.physx.plugin] ... possibly invalid inertia tensor of {1.0, 1.0, 1.0} and a negative mass, small sphere approximated inertia was used` | light_switch/outlet 등 일부 rigid body 의 mass property 가 불량 → 작은 구로 근사 | 장식요소 한정, 무시 |
| `[Warning] [omni.physx.cooking.plugin] UjitsoMeshCookingContext: cooking failure for .../cab_3_main_group/post_0_0` | cab_3 의 세로 기둥(post) 메시 쿠킹 실패 → 해당 prim 에 대해 triangle mesh collider 가 생성되지 않음 | 시각만 렌더링, 물리 충돌 없음 — 물건이 통과할 수 있으나 태스크엔 무관 |
| `[Warning] [gpu.foundation.plugin] ECC is enabled on physical device 0` | A4000 의 ECC 메모리가 켜진 상태 안내 | 정상 |
| `[Warning] [omni.isaac.dynamic_control] omni.isaac.dynamic_control is deprecated as of Isaac Sim 4.5` | 구 API 사용 안내 | Isaac Lab 2.3 내부 호출로 사용자가 손댈 일 없음, 무시 |
| `[Warning] [pxr.Semantics] pxr.Semantics is deprecated - please use Semantics instead` | USD 모듈 deprecation 안내 | 무시 |
| `[Warning] [omni.graph.core.plugin] Found duplicate of category 'Replicator'` | OGN 카테고리 중복 등록 | 무시 |
| `[Warning] [omni.replicator.core.scripts.extension] No material configuration file, adding configuration to material settings directly.` | Replicator 의 기본 머티리얼 config 파일 부재 | 무시 |
| `[Warning] [omni.fabric.plugin] Warning: attribute overrideClipRange not found for bucket id 9` | Fabric 내부 속성 lookup 실패 | 무시 |
| `[Warning] [omni.fabric.plugin] USD->Fabric: Unhandled array type string[]`<br>`[Warning] [usdrt.population.plugin] [UsdNoticeHandler] Unhandled attribute type VtArray<std::string> (prim attribute: omni:rtx:material:db:flattener:*)` | USD 의 string 배열 속성을 Fabric/USDRT 가 처리하지 못함 (RTX material db 관련) | 렌더링엔 영향 없음, 무시 |
| `[Warning] [omni.hydra] Parameter 'diffuse_texture_enable' of shade node ... not available in the MDL representation` | OmniPBR 머티리얼의 일부 파라미터가 MDL 변환본에 없음 | 렌더링 품질엔 영향 없음, 무시 |
| `[Warning] [rtx.postprocessing.plugin] DLSS increasing input dimensions: Render resolution of (371, 278) is below minimal input resolution of 300` | 뷰포트 해상도가 DLSS 최소치 미만이라 자동 상향 | 정상 |
| `[Warning] [omni.physx.plugin] Damping attribute is unsupported for articulation joints and will be ignored (.../sink_main_group/joints/handle)` | 싱크대 articulation joint 의 damping 속성은 PhysX 에서 무시됨 | 무시 |
| `[Warning] [omni.fabric.plugin] getAttributeCount/getTypes called on non-existent path .../Robot/wrist/visuals/wrist_roll_pitch_so101_v2` | SO-101 wrist visual prim 의 attribute 조회 시점 문제 | 로봇 제어엔 영향 없음, 무시 |
| `[Warning] [carb] Client gpu.foundation.plugin has acquired [gpu::unstable::IMemoryBudgetManagerFactory v0.1] 100 times. Consider accessing this interface with carb::getCachedInterface()` | Carb 인터페이스 획득 회수가 많다는 성능 권고 | 무시 |
| `[Warning] [omni.kit.notification_manager.manager] Physics USD Load: ...` (같은 메시지가 기동 후 수십 초 지나 다시 반복) | `R`/`N` 키로 reset 하면 씬이 재로드되면서 동일 경고들이 재출력 | 정상 동작 |

### 실제로 주의해야 할 로그

위 표에 해당하지 **않는** 다음 유형이 나오면 조치가 필요하다:

- `Windows fatal exception: code 0xc0000139` → **HDF5 ABI 불일치** (앞선 섹션 참조)
- kit log 백트레이스에 `arrow.dll` / `arrow_python.dll` / `_dataset.cp311-win_amd64.pyd` → **PyArrow / NumPy ABI 불일치** (앞선 섹션 참조)
- `ConnectionError: Could not connect on port 'COMx'` → 리더 암 시리얼 연결 실패. 포트 번호 / 드라이버 확인
- `AssertionError: the dataset file already exists, please use '--resume' to resume recording` → 기존 데이터셋 파일 삭제하거나 `--resume` 플래그 추가
- `Crash detected in pid ... thread ...` + `carb.crashreporter-breakpad.plugin` → 실제 프로세스 크래시. 직전에 찍힌 Python traceback 을 분석해야 함