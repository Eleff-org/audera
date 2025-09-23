     ________  ___  ___  ________  _______  ________  ________     
    |\   __  \|\  \|\  \|\   ___ \|\   ___\|\   __  \|\   __  \    
    \ \  \|\  \ \  \\\  \ \  \_|\ \ \  \__|\ \  \|\  \ \  \|\  \   
     \ \   __  \ \  \\\  \ \  \ \\ \ \   __\\ \      /\ \   __  \  
      \ \  \ \  \ \  \\\  \ \  \_\\ \ \  \_|_\ \  \  \ \ \  \ \  \ 
       \ \__\ \__\ \______/\ \______/\ \______\ \__\\ _\\ \__\ \__\
        \|__|\|__|\|______| \|______| \|______|\|__|\|__|\|__|\|__|

`alpha-release` coming soon!

`audera` is an open-source multi-room audio streaming system written in Python for DIY home audio enthusiasts.

## Architecture overview

Audera uses a sophisticated **orchestrator pattern** to ensure reliable, high-performance audio streaming:

- **Isolated execution**: Critical I/O and timing-sensitive tasks run in dedicated thread pools
- **Event loop protection**: Main asyncio event loop stays responsive for coordination
- **Automatic recovery**: Failed tasks restart automatically with configurable timeouts
- **Resource management**: Thread pools prevent resource exhaustion under load

### Orchestrator Benefits

- **Zero Blocking**: I/O operations never freeze the event loop
- **Timing Precision**: Critical synchronization maintains sub-millisecond accuracy
- **Automatic Recovery**: Failed tasks restart with configurable retry logic
- **Resource Efficiency**: Thread pools scale with system capabilities
- **Operational Control**: Dynamic start/stop of services via orchestrator API

## How `audera` works

The streamer and player applications use an **orchestrator** to isolate critical tasks from blocking the main asynchronous event loop. Tasks involving I/O operations, timing-critical synchronization, or blocking operations are executed in dedicated thread pools, while lightweight coordination tasks run in the main event loop.

### Streamer

The streamer service isolates the following critical tasks:
- **Network time protocol (NTP) synchronization** - Timing-critical network I/O
- **Remote audio output player mDNS browsing** - Network discovery with player synchronization
- **Audio stream capturing and broadcasting** - Blocking audio I/O operations

#### Orchestrated task flow

```mermaid
graph TD
    A[Streamer Service] --> B[Main Event Loop]
    B --> C[Orchestrator]

    C --> D[NTP Synchronizer<br/>Thread Pool]
    C --> E[mDNS Browser<br/>Thread Pool]
    C --> F[Audio Streamer<br/>Thread Pool]

    D --> G[Network Time Sync<br/>Every 600s]
    E --> H[Player Discovery & Sync<br/>Every 5s]
    F --> I[Audio Capture & Broadcast<br/>Continuous]

    G -.-> B
    H -.-> B
    I -.-> B

    style B fill:#e1f5fe
    style C fill:#fff3e0
    style D fill:#c8e6c9
    style E fill:#c8e6c9
    style F fill:#c8e6c9
```

#### Getting Started

The streamer service automatically orchestrates all critical tasks for reliable audio streaming. Run from the command-line:

```bash
audera run streamer
```

Or through a Python session:

```python
import asyncio
import audera

if __name__ == '__main__':
    asyncio.run(audera.streamer.Service().run())
```

### Player

The player service isolates the following critical tasks:
- **Shairport-sync service monitoring** - Subprocess management of shairport-sync for Airplay2 connectivity
- **mDNS broadcasting** - Network service discovery I/O
- **Streamer synchronization** - Timing-critical clock synchronization
- **Audio stream receiving** - Audio packet I/O operations
- **Audio playback** - Blocking audio output operations

#### Orchestrated Task Flow

```mermaid
graph TD
    A[Player Service] --> B[Main Event Loop]
    B --> C[Orchestrator]

    C --> D[Shairport-Sync Monitor<br/>Thread Pool]
    C --> E[mDNS Broadcaster<br/>Thread Pool]
    C --> F[Streamer Synchronizer<br/>Thread Pool]
    C --> G[Audio Receiver<br/>Thread Pool]
    C --> H[Audio Playback<br/>Thread Pool]

    D --> I[Service Status Check<br/>Every 5s]
    E --> J[Service Broadcasting<br/>Continuous]
    F --> K[Time Synchronization<br/>Continuous]
    G --> L[Packet Reception<br/>Continuous]
    H --> M[Audio Output<br/>Continuous]

    I -.-> B
    J -.-> B
    K -.-> B
    L -.-> B
    M -.-> B

    style B fill:#e1f5fe
    style C fill:#fff3e0
    style D fill:#ffcdd2
    style E fill:#c8e6c9
    style F fill:#c8e6c9
    style G fill:#c8e6c9
    style H fill:#c8e6c9

    D:::deprecated
    classDef deprecated fill:#ffcdd2,stroke:#d32f2f,stroke-width:2px
```

#### Getting Started

The player service uses full task orchestration for optimal audio playback performance. Run from the command-line:

```bash
audera run player
```

Or through a Python session:

```python
import asyncio
import audera

if __name__ == '__main__':
    asyncio.run(audera.player.Service().run())
```