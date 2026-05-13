# SO-ARM101 VLA Control System

SO-ARM101 6축 로봇 팔에 대한 VLA(Vision-Language-Action) 기반 제어 시스템. Hugging Face **LeRobot** + **LeIsaac** (NVIDIA Isaac Sim) 조합으로 시뮬레이션 학습과 실기기 텔레오퍼레이션을 모두 지원한다.

## 목차 <!-- omit in toc -->

- [아키텍처](#아키텍처)
- [환경 요구사항](#환경-요구사항)
- [설치 및 사용 방법](#설치-및-사용-방법)
- [Reference](#reference)


## 아키텍처

### 시뮬레이션 경로 (LeIsaac + Isaac Sim)

```
[SO-ARM101 리더 암] → teleop_se3_agent.py → Isaac Sim 씬 제어
                                ↓
                        HDF5 에피소드 기록 (./datasets/dataset.hdf5)
                                ↓
                          isaaclab2lerobot 변환
                                ↓
                    LeRobot 호환 데이터셋 → HF Hub
```

### 실기기 경로 (LeRobot)

```
[SO-ARM101 리더 암] → lerobot-record → [LeRobot 데이터셋] → HF Hub
                                           ↓
                                    lerobot-train (ACT / SmolVLA)
                                           ↓
                           outputs/train/*/checkpoints/last/
                                           ↓
                                    hf upload
                                           ↓
                                [HF Hub 모델 저장소]
                                           ↓
                                  lerobot-eval (추론)
                                           ↓
                               [SO-ARM101 팔로워 암 실행]
```

## 환경 요구사항

### 소프트웨어

| 항목 | 버전 | 비고 |
|------|------|------|
| Ubuntu 24.04 | (Windows)WSL2 커널 6.6+ 권장 |
| Docker | 최신 | (Windows)WSL2 backend 활성화 필수 |
| usbipd-win | 5.0 이상 | (Windows)USB 장치 WSL2 포워딩 |
| NVIDIA Driver | 580 이상 | CUDA 컨테이너 실행용 |
| NVIDIA Container Toolkit | 12.8 이상 | Docker GPU 지원 |
| Hugging Face 계정 | - | 데이터셋·모델 업로드·다운로드용 |
| W&B 계정 | - | 모델 학습 기록용 |

### 하드웨어

| 장치 | 수량 | 비고 |
|------|------|------|
| NVIIDA GPU | 1개 이상 | (Isaac Sim)RT 코어 필수. Isaac Sim 5.1은 카메라 sensor·뷰포트 렌더링 모두 RTX raytracing pipeline 위에서만 동작. NVIDIA 공식 문서가 *"GPUs without RT Cores (A100, H100) are not supported."* 라고 H100/A100을 명시적으로 제외 ([Isaac Sim 5.1 System Requirements](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html)). 권장 GPU는 GeForce RTX 4080(최소) / RTX 5080(양호) / RTX PRO 6000 Blackwell. VRAM 최소 16 GB |
| SO-101 Leader Arm | 1 | Feetech STS3215 서보 |
| SO-101 Follower Arm | 1 | Feetech STS3215 서보 |
| USB-Serial 어댑터 | 2 | CH343 칩 (COM 포트) |
| 카메라 | 2 | belly cam (전면), wrist cam (손목) |

### 핵심 의존성

버전은 `pyproject.toml` 에 고정

| 패키지 | 버전 | 비고 |
|--------|------|------|
| Python | 3.11 | - |
| torch  | 2.7.0 | - |
| isaacsim | 5.1.0 | `[all,extscache]` extras 포함 |
| isaaclab | 2.3.0 | `leisaac[isaaclab]` 로 간접 설치 |
| leisaac | 0.4.0 | `pyproject.toml` 의 `[tool.uv.sources]` 가 git tag `v0.4.0` 에서 설치 |
| lerobot | 0.4.4 | - |

## 설치 및 사용 방법

### LeRobot 이미지 빌드

```bash
docker compose -f docker/docker-compose.yaml build lerobot
```

### (WSL)USB 포트 연결

SO-101 Leader Arm, Follower Arm, 카메라들을 컴퓨터에 연결

이후 관리자 권한으로 powershell 열어서 usbipd 설치 후 포트 바인딩 진행

```powershell
# usbipd 설치
winget install usdipd
# 포트 목록 조회
usbipd list
# 최초 1회만 실행
usbipd bind --busid <leader-port>
usbipd bind --busid <follower-port>
usbipd bind --busid <wrist-cam-port>
usbipd bind --busid <belly-cam-port>
# usb 재연결할 때마다 / WSL 리부트할 때마다 실행
usbipd attach --wsl --busid <leader-port>
usbipd attach --wsl --busid <follower-port>
usbipd attach --wsl --busid <wrist-cam-port>
usbipd attach --wsl --busid <belly-cam-port>
# Windows로 포트를 되돌릴 경우:
usbipd detach --busid <port>
```

이후 wsl에서 포트 권한 설정 진행

```bash
# Leader Arm, Follower Arm USB
sudo chmod 666 /dev/ttyACM0 /dev/ttyACM1
# Wrist Cam, Belly Cam
sudo chmod 666 /dev/video0 /dev/video2
sudo usermod -aG dialout $USER
```

### .env 파일 작성

`.env.example` 파일을 `.env` 파일로 복사한 후 다음 값을 입력

| 이름 | 설명 |
|-----|------|
|HF_TOKEN | Hugging Face 토큰(발급: [Hugging Face settings](https://huggingface.co/settings/tokens)) |
| HF_USER | Hugging Face 계정 이름 |
| WANDB_API_KEY | Weight & Bias API 키(발급: [wandb 설정](https://wandb.ai/settings)) |



```bash
cp .env.example .env
```

### SO-101 Motor Setup

`.env` 파일에서 다음 인자들을 입력하고 docker 명령어 실행

| 이름 | 설명 |
|---|-----|
| CALIBRATE_TARGET | `robot`: 팔로워 암 모터 설정, `teleop`: 리더 암 모터 설정
| TELEOP_PORT | 리더 암 포트(예: `/dev/ttyACM0`) |
| ROBOT_PORT | 팔로워 암 포트(예: `/dev/ttyACM1`) |

```bash
# CALIBRATE_TARGET을 robot / teleop으로 설정하고 각각 1회 실행
docker compose --env-file .env -f docker/docker-compose.yaml run \
    --rm lerobot setup-motors
```

### SO-101 Calibration

`.env` 파일에서 다음 인자들을 입력하고 docker 명령어 실행

| 이름 | 설명 |
|---|-----|
| CALIBRATE_TARGET | `robot`: 팔로워 암 모터 설정, `teleop`: 리더 암 모터 설정
| TELEOP_PORT | 리더 암 포트(예: `/dev/ttyACM0`) |
| TELEOP_ID | 리더 암 아이디(예: `so101_teleop`) |
| ROBOT_PORT | 팔로워 암 포트(예: `/dev/ttyACM1`) |
| ROBOT_ID | 팔로워 암 아이디(예: `so101_robot`) |

```bash
# CALIBRATE_TARGET을 robot / teleop으로 설정하고 각각 1회 실행
docker compose --env-file .env -f docker/docker-compose.yaml run \
    --rm lerobot calibrate
```

### SO-101 Teleoperation

`.env` 파일에서 다음 인자들을 입력하고 docker 명령어 실행

`--display_data=true`로 할 경우, 호스트 환경에서 `pip install rerun-sdk==0.26.2; rerun`을 먼저 실행

| 이름 | 설명 |
|-----|------|
| BELLY_CAM_PORT | 전면부 카메라 포트(예: `/dev/video0`) |
| WRIST_CAM_PORT | 그리퍼 카메라 포트(예: `/dev/video2`) |
| CAM_WIDTH | 카메라 가로 픽셀 |
| CAM_HEIGHT | 카메라 세로 픽셀 |
| CAM_FPS | 카메라 FPS |
| CAM_FOURCC | 카메라 fourcc 코드(예: `MJPG`) |
| DISPLAY_DATA | 데이터 시각화 여부(예: `false`) |
| DISPLAY_IP | 데이터를 송출할 IP, docker에서 실행할 경우 `host.docker.interal` |
| DISPLAY_PORT | 데이터 송출 포트, 기본값 `9876` |
| TELEOP_EXTRA_ARGS | 기타 인자 |

```bash
docker compose --env-file .env -f docker/docker-compose.yaml run \
    --rm lerobot teleop
```

### 데이터셋 녹화

`.env` 파일에서 다음 인자들을 입력하고 docker 명령어 실행

`--display_data=true`로 할 경우, 호스트 환경에서 `pip install rerun-sdk==0.26.2; rerun`을 먼저 실행

| 이름 | 설명 |
|-----|------|
| SINGLE_TASK | 에피소드 작업 설명, snake case로 작성 |
| NUM_EPISODES | 수집할 에피소드 수 |
| EPISODE_TIME_S | 에피소드당 녹화 시간(초) |
| RESET_TIME_S | 에피소드당 환경 초기화 대기 시간(초) |
| RECORD_FPS | 데이터셋 저장 FPS, teleop FPS와 별도 |
| PUSH_TO_HUB | Hugging Face 데이터 업로드 여부 |
| DATA_ROOT | 데이터셋 저장 경로 |
| RECORD_EXTRA_ARGS | 기타 인자 |

녹화 중 다음과 같이 키보드로 조작할 수 있음

| 키 | 기능 |
|----|-----|
| → | 에피소드 조기 종료 |
| ← | 현재 에피소드를 취소하고 다시 녹화 |
| ESC | 즉시 세션을 종료하고 비디오 인코딩 + 데이터셋 업로드 |

```bash
docker compose --env-file .env -f docker/docker-compose.yaml run \
    --rm lerobot record
```

### Policy 학습

`.env` 파일에서 다음 인자들을 입력하고 docker 명령어 실행

| 이름 | 설명 |
|-----|------|
| HF_DATASET_REPO_ID | 학습 데이터셋 HF Hub ID, 기본값은 ${HF_USER}/${SINGLE_TASK} |
| DATA_ROOT | 데이터셋 로컬 저장 루트 |
| POLICY_TYPE | Policy 종류(목록은 [여기](https://github.com/huggingface/lerobot/tree/v0.5.1/src/lerobot/policies)에서 확인) |
| JOB_NAME | 실험 이름(WandB에 표시) |
| BATCH_SIZE | 배치 크기(기본값은 8) |
| TRAIN_STEPS | 총 학습 스텝 수(기본값은 100,000)
| OUTPUT_DIR | 체크포인트, 로그 출력 디렉터리(기본값은 `outputs/train/${JOB_NAME}`) |
| DEVICE | 가속기 종류(예: `cuda`) |
| WANDB_ENABLE | wandb 연동 여부 |


```bash
docker compose --env-file .env -f docker/docker-compose.yaml run \
    --rm lerobot train \
        --dataset.repo_id=${HF_DATASET_REPO_ID} \
        --policy.type=${POLICY_TYPE} \
        --output_dir=${OUTPUT_DIR} \
        --steps=${TRAIN_STEPS} \
        --batch_size=${BATCH_SIZE} \
        --wandb.enable=${WANDB_ENABLE} \
        ${TRAIN_EXTRA_ARGS}
```

### Policy 평가 및 추론

`.env` 파일에서 다음 인자들을 입력하고 docker 명령어 실행

| 이름 | 설명 |
|-----|------|
| POLICY_PATH | 사전학습 체크포인트 경로/Hub ID |

```bash
docker compose --env-file .env -f docker/docker-compose.yaml run \
    --rm lerobot record \
        --robot.type=so101_follower \
        --robot.port=${ROBOT_PORT} \
        --robot.cameras="{
            wrist: {type: opencv, index_or_path: ${WRIST_CAM_PORT}, width: ${CAM_WIDTH}, height: ${CAM_HEIGHT}, fps: ${CAM_FPS}, warmup_s: ${CAM_WARMUP_S}, fourcc: ${CAM_FOURCC}},
            belly: {type: opencv, index_or_path: ${BELLY_CAM_PORT}, width: ${CAM_WIDTH}, height: ${CAM_HEIGHT}, fps: ${CAM_FPS}, warmup_s: ${CAM_WARMUP_S}, fourcc: ${CAM_FOURCC}},
            }" \
        --robot.id=${ROBOT_ID} \
        --teleop.type=so101_leader \
        --teleop.port=${TELEOP_PORT} \
        --teleop.id=${TELEOP_ID} \
        --dataset.single_task=${SINGLE_TASK} \
        --dataset.repo_id=${HF_USER}/${SINGLE_TASK} \
        --dataset.num_episodes=${NUM_EPISODES} \
        --dataset.episode_time_s=${EPISODE_TIME_S} \
        --dataset.reset_time_s=${RESET_TIME_S} \
        --dataset.push_to_hub=${PUS_TO_HUB} \
        --dataset.fps=${RECORD_FPS} \
        --dataset.root=${DATA_ROOT} \
        ${RECORD_EXTRA_ARGS} \
        --policy.path=${POLICY_PATH}
```

## Reference

- [Isaac Sim 5.1 + Isaac Lab 2.3 + LeIsaac on Windows](https://hackmd.io/@asierarranz/rkg1tvT93gx)
- [Installation | LeIsaac Document](https://lightwheelai.github.io/leisaac/docs/getting_started/teleoperation)
- [Teleoperation | LeIsaac Document](https://lightwheelai.github.io/leisaac/docs/getting_started/teleoperation)
- [Policy Training & Inference | LeIsaac Document](https://lightwheelai.github.io/leisaac/docs/getting_started/policy_support)
- [Post-Training Isaac GR00T N1.5 for LeRobot SO-101 Arm](https://huggingface.co/blog/nvidia/gr00t-n1-5-so101-tuning)
- [Train an SO-101 Robot From Sim-to-Real With NVIDIA Isaac — Train an SO-101 Robot From Sim-to-Real With NVIDIA Isaac](https://docs.nvidia.com/learning/physical-ai/sim-to-real-so-101/latest/index.html)
- [isaac-sim/Sim-to-Real-SO-101-Workshop: This code supports learning content to demonstrate an end-to-end Physical AI workflow with the SO-101 robot, Isaac Lab, and Isaac GR00T.](https://github.com/isaac-sim/Sim-to-Real-SO-101-Workshop)
