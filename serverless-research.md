# Migrating lingling to serverless functions: feasibility research

Date of verification: 2026-10-25, read from the machine environment block, not from
my own sense of the present. Each "Last updated" date below is the one printed on the
source page itself.

What was read: the repository at /workspace/lingling (all 15 modules plus tools/), and
the primary documentation for each platform. What was NOT done: nothing was run. No
function was deployed and no limit was exercised. Every claim below is either quoted
from a source page or explicitly marked as inference.

Source repository: https://github.com/huranth/lingling

---

## 1. What the application is, from the source

A Python 3.11+ CLI (`lingling`) that wraps the `opencode` CLI. It exists to spread one
client's model traffic across about ten Tor exit relays in different countries, and to
race each request over five of them at once.

- `lanes.py` spawns one `tor` process per lane via `stem.process.launch_tor_with_config`
  with `take_ownership=True` (`lanes.py::_launch_tor_process`), each with its own
  `DataDirectory`, `SocksPort` and `ControlPort`, and supervises them across the
  session through `restart_lane`, `regenerate_lane`, `_defer_rebuild` and `claim_move`.
- `relay.py` runs an asyncio CONNECT proxy on `127.0.0.1` on its own thread
  (`Relay._run`), dups the accepted socket and hands it to a MITM thread.
- `mitm.py` mints a local root CA (`_ensure_ca`, RSA 2048, 10 year validity) and
  per-host leaf certs (`CertShop.context_for`), terminates the client's TLS, reads the
  model name out of the body (`_model_of`), then races the call over `_RACE_WIDTH`,
  default 5, lanes at once, and the first 200 takes the client (`_Race.claim`, while
  `_Copy.beat` closes the losers).
- `cli.py::_session` sets `HTTPS_PROXY` to `http://127.0.0.1:<port>` and
  `NODE_EXTRA_CA_CERTS` to the CA path in the child environment, then calls
  `subprocess.Popen([opencode, *args], env=env)` and waits.
- `netutil.py::session_lock` uses `fcntl.flock` on POSIX or `msvcrt.locking` on Windows,
  on a file descriptor held for the process lifetime, plus a PID file.
- `proof.py::spawn_proof_window` opens a second terminal process
  (`CREATE_NEW_CONSOLE`, `wt`, `gnome-terminal`, `konsole`, `xterm`) tailing a JSONL log.
- `bench.py` holds five JSON ledgers on disk: `limited-exits.json`, `exit-spend.json`,
  `used-exits.json`, `verified-exits.json`, `country-scores.json`.
- `winjob.py` uses ctypes and Windows Job Objects so `tor.exe` dies with the parent.

The repo already contains one serverless function: `tools/update-api/api/latest.py`,
deployed at https://lingling-update.vercel.app/api/latest

---

## 2. Platform constraint table (all verified 2026-10-25 against the cited page)

### AWS Lambda

| Constraint | Value (2026) | Source |
|---|---|---|
| Max duration, synchronous | 900 s (15 min) | https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html |
| Max duration, Managed Instances async/ESM | 5,400 s (90 min), a 6x increase; synchronous stays at 900 s | https://aws.amazon.com/about-aws/whats-new/2026/09/aws-lambda-90-minute-function/ and https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html |
| Max memory | 128 MB to 10,240 MB in 1 MB steps; 1 vCPU at 1,769 MB | https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html |
| /tmp storage | 512 MB to 10,240 MB, configurable | https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html |
| /tmp persistence | Survives a freeze and an invoke-failure reset. Quoted: "Lambda terminates execution environments every few hours to allow for runtime updates and maintenance, even for functions that are invoked continuously. You should not assume that the execution environment will persist indefinitely." | https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html |
| Child processes | Permitted. Quoted: "Background processes or callbacks that were initiated by your Lambda function and did not complete when the function ended resume if Lambda reuses the execution environment." | same page |
| Environment freeze | Quoted: "Lambda freezes the execution environment when the runtime and each extension have completed and there are no pending events." | same page |
| Processes and threads per env | 1,024 | https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html |
| File descriptors | 1,024 | same |
| Concurrency | 1,000 default, soft, increasable to "tens of thousands"; scaling 1,000 execution environments per 10 seconds | same |
| Deployment package | 50 MB zipped, 250 MB unzipped; container image 10 GB uncompressed | same |
| Sync payload | 6 MB request and response; 200 MB streamed response; 2 MB/s beyond the first 6 MB | same |
| Network bandwidth | 625 Mbps per execution environment, raisable | same |
| Init phase | 10 s for on-demand concurrency; up to 15 min for provisioned concurrency, SnapStart and Managed Instances | https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtime-environment.html |
| Cold start, generic | Quoted: "Cold starts typically occur in under 1% of invocations. The duration of a cold start varies from under 100 ms to over 1 second." | same page |
| Managed Instances model | Runs on customer-owned EC2. Quoted: "the execution environment remains continuously active, processing invocations as they arrive without freezing between invocations"; parallel invocations per environment; "Independent timeouts" per invocation | https://docs.aws.amazon.com/lambda/latest/dg/lambda-managed-instances-execution-environment.html |
| Lambda MicroVMs | Max execution 8 hours (28,800 s) per MicroVM; 8 concurrent connections at 1 vCPU | https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html |

### Google Cloud Run

| Constraint | Value (2026) | Source |
|---|---|---|
| Request timeout | Default 300 s, max 3,600 s (60 min) | https://docs.cloud.google.com/run/docs/configuring/request-timeout |
| vCPU | Default 1, max 8, min 0.08 | https://docs.cloud.google.com/run/docs/configuring/services/cpu |
| Memory | Max 32 GiB per container instance | https://docs.cloud.google.com/run/quotas |
| Writable in-memory filesystem | 32 GiB, limited by instance memory | same |
| Startup timeout | 4 minutes per container instance | same |
| CPU allocation | Request-based (default, CPU only during request processing) versus instance-based (CPU for the entire container instance lifecycle; formerly "CPU always allocated") | https://docs.cloud.google.com/run/docs/configuring/billing-settings |
| Background processes | Quoted: "An instance will never stay idle for more than 15 minutes after processing a request unless it is kept active using minimum instances." | same |
| Shutdown grace | 10 seconds after SIGTERM | same |
| Min instances | Default 0. Best effort. Quoted: "You might experience temporary drops below your configured minimum instances" | https://docs.cloud.google.com/run/docs/configuring/min-instances |
| Cloud Run instances, the singleton resource | Max continuous execution time before automatic restart: 7 days, requires always or on-failure restart policy | https://docs.cloud.google.com/run/quotas |
| Shared CPU baseline | 6.25% baseline vCPU with bursting to 100%, for Cloud Run instances | https://docs.cloud.google.com/run/quotas and https://docs.cloud.google.com/run/docs/configuring/billing-settings |
| HTTP/1 request and response size | 32 MiB each; no limit if using HTTP/2, or Transfer-Encoding chunked, or streaming | https://docs.cloud.google.com/run/quotas |
| Concurrent requests | 80 per instance (services default 1,000); 100 concurrent streams per HTTP/2 client connection | same |
| Open connections | 50,000 per instance per egress type | same |
| Outbound connections | 700 per second and 5,000 per minute per instance | same |
| Pricing, us-central1 | Instance-based: 0.000018 USD per vCPU-second and 0.000002 USD per GiB-second. Free tier 240,000 vCPU-seconds and 450,000 GiB-seconds per month. Request-based: 0.000024 per vCPU-second active, 0.0000025 idle, 0.0000025 per GiB-second, 0.40 USD per million requests | https://cloud.google.com/run/pricing |

### Cloudflare Workers

| Constraint | Value (2026) | Source |
|---|---|---|
| Runtime model | V8 isolates. Python runs on Pyodide, CPython compiled to WebAssembly | https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/ |
| CPU time | Free 10 ms; Paid 5 min, default 30 s | https://developers.cloudflare.com/workers/platform/limits/ |
| Memory | 128 MB per isolate, not per invocation | same |
| Duration | HTTP request: no hard limit while the client remains connected. Cron Trigger 15 min. Queue consumer 15 min. Durable Object alarm 15 min. Durable Objects over RPC or HTTP: unlimited while the caller stays connected | same |
| waitUntil | Extends execution up to 30 seconds after the response is sent or the client disconnects | same |
| Subrequests | Free 50 per invocation; Paid 10,000 | same |
| Simultaneous outgoing connections | 6 per invocation, counted while waiting for response headers | same |
| Worker size and startup | 64 MiB uncompressed; 1 second startup CPU budget | same |
| Raw TCP | connect() imported from cloudflare:sockets, with secureTransport of off, on or starttls | https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/ |
| TCP blocks | Quoted: "Outbound TCP sockets to Cloudflare IP ranges are blocked." Quoted: "Examples of a disallowed address include Cloudflare IPs, localhost, and private network IPs." Port 25 prohibited. "TCP Loop detected" when connecting back to the same Worker | same |
| TCP socket lifetime | Quoted: "TCP sockets cannot be created in global scope and shared across requests. You should always create TCP sockets within a handler (ex: fetch(), scheduled(), queue()) or alarm()." | same |
| Durable Object plus TCP | Quoted: "an open TCP socket keeps the Durable Object in memory and causes it to incur duration charges for up to 15 minutes per connection" | same |
| Inbound TCP | Only via a connect() handler forwarded from another Worker over a service binding. Quoted: "Support for handling inbound TCP connections from other sources is coming soon." | same |
| Python stdlib exclusions | Not available: curses, dbm, ensurepip, fcntl, grp, idlelib, lib2to3, msvcrt, pwd, resource, syslog, termios, tkinter, turtle, turtledemo, venv, winreg, winsound. pty and tty cannot be imported. Quoted: multiprocessing and threading "can be imported, but are not functional due to the limitations of the WebAssembly VM" | https://developers.cloudflare.com/workers/languages/python/stdlib/ |
| Filesystem | Quoted: "ephemeral, in-memory filesystem"; "all data is lost when the Worker isolate is destroyed"; "The filesystem is not shared between different isolate instances" | same |
| Python packages | Quoted: "Python Workers support pure and PyEmscripten Python packages on PyPI" plus packages included in Pyodide | https://developers.cloudflare.com/workers/languages/python/packages/ |
| Free requests | 100,000 per day, resetting at midnight UTC | https://developers.cloudflare.com/workers/platform/limits/ |
| Response body | No enforced limit; CDN cache limits are 512 MB on Free, Pro and Business, 5 GB on Enterprise | same |

### Vercel

| Constraint | Value (2026) | Source |
|---|---|---|
| Max duration | Hobby: 300 s default and maximum. Pro and Enterprise: 300 s default, 800 s maximum, 1800 s extended maximum in Beta | https://vercel.com/docs/functions/limitations and https://vercel.com/docs/functions/configuring-functions/duration |
| Extended duration runtimes | nodejs22.x, nodejs24.x, Bun 1.x and 1.4.x, python3.12, python3.13, python3.14. Pro and Enterprise only. Secure Compute and Static IPs do not support durations above 800 s during the beta | https://vercel.com/docs/functions/configuring-functions/duration |
| Memory | Hobby 2 GB and 1 vCPU. Pro and Enterprise default 2 GB and 1 vCPU, maximum 4 GB and 2 vCPU | https://vercel.com/docs/functions/limitations |
| Bundle size | 250 MB uncompressed; 500 MB for Python; Large Functions beta up to 5 GB on Node.js, Bun and Python | same |
| Request and response body | 4.5 MB maximum, returning 413 FUNCTION_PAYLOAD_TOO_LARGE above it | same |
| File descriptors | 1,024 shared across all concurrent executions, including runtime usage | same |
| Concurrency | Auto-scales up to 30,000 on Hobby and Pro, or 100,000+ on Enterprise | same |
| Python versions | 3.12 (default), 3.13, 3.14 | https://vercel.com/docs/functions/runtimes/python |
| Streaming | Supported on the Python runtime | same |
| Edge runtime | Must begin sending a response within 25 s to keep streaming, and can stream for up to 300 s | https://vercel.com/docs/functions/limitations |
| Underlying platform | Vercel Functions run on AWS Lambda. The docs list AWS_EXECUTION_ENV, LAMBDA_TASK_ROOT and related variables as inaccessible under fluid compute, and state bundle limits are "enforced by AWS" | same |
| Daemons, Public Beta on all plans | Container-based long-running background processes. Memory 1, 2, 4 or 8 GiB, default 2 GiB. vCPUs 1, 1, 2 or 4 based on memory. SIGTERM with 30 s default grace, configurable to 3,600 s. Up to 100 instances per region per daemon. Max 50 daemon instances per project environment. CPU architecture linux amd64 | https://vercel.com/docs/daemons and https://vercel.com/docs/daemons/limits |
| Daemon quotas | Hobby: 5 Active CPU-hours per month. Pro: 16 vCPUs and 32 GiB of memory running at once. Enterprise: custom | https://vercel.com/docs/daemons/limits |
| Daemon exclusions | Quoted unsupported features: "Inbound HTTP or TCP traffic", "Autoscaling", "Persistent local storage", preview deployments, running in vercel dev, service bindings and rewrites | same |

### Azure Functions

| Constraint | Value (2026) | Source |
|---|---|---|
| Timeout, Flex Consumption | Default 30 min, maximum unbounded. 60 min grace during scale in, 10 min during platform updates | https://learn.microsoft.com/en-us/azure/azure-functions/functions-scale |
| Timeout, Premium, Dedicated, Container Apps | Default 30 min, maximum unbounded. Dedicated requires the App Service plan be set to Always On | same |
| Timeout, Consumption, legacy | Default 5 min, maximum 10 min | same |
| HTTP response cap | Quoted: "Regardless of the function app timeout setting, 230 seconds is the maximum amount of time that an HTTP triggered function can take to respond to a request. This limit exists because of the default idle timeout of Azure Load Balancer." | same |
| Worker startup | Maximum 60 seconds for the language-specific worker process to start, not configurable | same |
| Memory per instance | Flex Consumption 4 GB max, with instance sizes of 512 MB, 2,048 MB and 4,096 MB. Premium 3.5 to 14 GB. Dedicated 1.75 to 256 GB | same |
| Max instances | Flex Consumption 1,000. Premium 20 to 100 on Linux, 100 on Windows. Dedicated 10 to 30, or 100 in an ASE. Container Apps 300 to 1,000. Consumption 200 Windows and 100 Linux | same |
| Temporary storage | Flex Consumption 0.8 GB, with 0 GB persisted. Premium 11 to 61 GB temp and 250 GB persisted | same |
| Max request size | 210 MB | same |
| Max outbound connections per instance | Unbounded on Flex Consumption, Premium and Container Apps. Consumption is 600 active, 1,200 total | same |
| OS for Python | Quoted: "Linux is the only supported operating system for the Python runtime stack." | same |
| Plan retirement | Linux Consumption retires 30 September 2028. Function apps on the end-of-life v3 runtime on Linux in a Consumption plan stop running after 30 September 2026 | same |
| Scale-in grace | 60 minutes during scale in for Flex Consumption and Premium; 10 minutes during platform updates | same |

### Always-on alternatives, for part C

| Option | Verified price | Source |
|---|---|---|
| Fly.io shared-cpu-1x, 256 MB | 2.19 USD per 30 days, the smallest always-on app | https://fly.io/docs/about/pricing/ |
| Fly.io shared-cpu-1x, 512 MB and 1 GB | 3.69 and 6.70 USD per month | same |
| Fly.io shared-cpu-2x, 2 GB | 13.39 USD per month | same |
| Fly.io additional RAM | 6.00 USD per GB per month | same |
| Fly.io volumes and stopped rootfs | 0.15 USD per GB per month each | same |
| Fly.io egress | 0.02 USD per GB in North America and Europe; 0.04 in Asia Pacific, Oceania and South America; 0.12 in Africa and India | same |
| Fly.io free tier | None. The trial lasts up to 2 hours of Machine runtime or 7 days | same |
| Render web service | 7 USD per month for under 1 CPU and 512 MB; 25 USD for 1 CPU and 2 GB; 85 USD for 2 CPU and 4 GB. Persistent disks 0.25 USD per GB per month. Workspace plans: Hobby 0, Pro 25, Scale 499 USD per month | https://render.com/pricing |
| Railway | Hobby 5 USD per month including 5 USD of resource usage; Pro 20 USD per seat per month | https://docs.railway.com/pricing/plans |

---

## 3. Verdicts

### A. Genuinely serverless-shaped

**A1. The update manifest. Already done, and it is the right shape.**
`tools/update-api/api/latest.py` is a `BaseHTTPRequestHandler`, stdlib only, one GET, a
3 second upstream timeout, and `Vercel-CDN-Cache-Control` of
`max-age=300, stale-while-revalidate=86400`. It is a cached read of a third-party API
behind a CDN. This is the textbook serverless function and it is already deployed.
Nothing to change. Verified by reading the file and `update.py::MANIFEST_URL`.

**A2. The pure decision functions in `exits.py` and `bench.py`.**
`exits.claim`, `exits.headroom`, `exits.sweep_order`, `bench.bench_span`, `bench.day_of`
and `bench.next_free_reset` are pure functions of their arguments. Given a notepad
snapshot, a consensus snapshot and a clock, they return an answer with no I/O. They
port to any of the five platforms unchanged, since they are ordinary Python using
`random` and `ipaddress`. Verified by reading the source.

**A3. Consensus fetch, parse and rank, as a periodic job.**
`exits.load_relays` parses a microdesc consensus with `stem.descriptor.parse_file` and
groups exits by country via a geoip binary search. That is a batch job on a roughly
10 MB public input, run hourly. It fits comfortably on Lambda, with 10,240 MB memory,
10 GB of /tmp and 900 s, all far more than a parse needs. It does NOT fit Cloudflare
Workers well: 128 MB per isolate, and a Pyodide/WASM parse of a 10 MB consensus is a
different performance animal. That was not measured, so no number is offered.

**A4. Proof-event ingestion.**
`proof.make_emitter` appends JSON lines. The append half is a stateless POST and ports
trivially.

**A5. A remote proof viewer, but only if you accept moving the pane off the machine.**
Cloudflare Workers have no hard duration limit for HTTP while the client stays
connected, and Durable Objects can hold a WebSocket indefinitely. A web-based live tail
is achievable there. It is not the same product as a second console window next to the
editor, and it changes the trust story: the proof pane's whole argument is "it is on
your machine".

### B. Fundamentally impossible, with the named constraint

**B1. Spawning and supervising 10 long-lived `tor` processes.**

- Cloudflare Workers: hard block, verified. `multiprocessing` and `threading` are
  documented as importable but "not functional due to the limitations of the
  WebAssembly VM". There is no fork or exec in a V8 isolate running Pyodide. The 30 MB
  Tor Expert Bundle cannot be unpacked into an isolate, and the filesystem is
  explicitly "not shared between different isolate instances".
- Vercel Functions: hard block, verified. 300 s on Hobby, 800 s on Pro and Enterprise,
  1800 s in the extended beta. A coding session is hours.
- Azure Functions: soft. Flex Consumption and Premium have unbounded timeout, so a
  single invocation could in principle hold the fleet. But that is an App Service plan
  wearing a function costume, and the 230 second HTTP response cap still bites (B5).
- AWS Lambda: near block, verified. You can spawn children, and unfinished background
  processes do resume when the environment is reused. But the environment freezes
  between invocations, and "Lambda terminates execution environments every few hours
  to allow for runtime updates and maintenance, even for functions that are invoked
  continuously". A frozen supervisor is not a supervisor. The 900 s synchronous cap
  sits on top.
- Google Cloud Run: the one function product where this works. A container can spawn
  processes, and with instance-based billing plus minimum instances, "An instance will
  never stay idle for more than 15 minutes after processing a request unless it is kept
  active using minimum instances". So a Cloud Run service with min instances 1 and
  instance-based billing can hold 10 tor processes indefinitely. This is not really
  serverless any more, it is a container that happens to be managed, and Google says so
  itself by pointing single long-lived workloads at the Cloud Run instances resource,
  which runs up to 7 days before automatic restart.

**B2. Holding a MITM CA and intercepting a local client's TLS. Blocked by architecture,
not by quota.**

Two things must happen on the user's machine, and only the user's machine can do them.
First, `cli.py::_session` writes `HTTPS_PROXY` and `NODE_EXTRA_CA_CERTS` into the
environment of the opencode child process. Second, something must be listening on that
port on 127.0.0.1. No function platform can do either. Cloudflare blocks it outright
and explicitly: connecting to localhost returns "proxy request failed, cannot connect
to the specified address". Lambda, Vercel and Azure functions are invoked over public
HTTPS and have no listener on a laptop. Cloud Run can serve a public endpoint, but
opencode is configured to talk to 127.0.0.1.

Two secondary blockers, worth naming separately.

The `cryptography` package cannot be bundled on Cloudflare. The documented policy is
"Python Workers support pure and PyEmscripten Python packages on PyPI", and
`cryptography` ships Rust and C extensions. Inference: no PyEmscripten wheel exists, so
the CA cannot be minted there. The policy was verified, not the wheel index.

The CA private key would leave the user's machine. `_ensure_ca` writes `ca-key.pem` with
mode 0600 into the per-user data directory (verified by reading `mitm.py`). To mint leaf
certs server side you would ship that key to a provider. That is a security decision,
not a porting detail.

**B3. A localhost CONNECT proxy. Same root cause as B2.**
`relay.py::_serve` binds 127.0.0.1 (verified by reading `relay.py`). Cloudflare's
`connect()` blocks localhost and private ranges by name. Lambda, Vercel and Azure have
no inbound TCP from a client machine at all. Cloudflare's inbound TCP path is a
`connect()` handler reachable only from another Worker over a service binding, with
general inbound support "coming soon". All verified.

**B4. Racing 5 lanes and cancelling the losers.**
The race itself is easy anywhere. Three parts are not.

Cancellation. `_Copy.beat` closes the losing socket from the winning thread (verified by
reading `mitm.py`). On Cloudflare this collides with "TCP sockets cannot be created in
global scope and shared across requests", so the 10 SOCKS5 tunnels cannot be persistent
objects an invocation reaches into. Verified.

Connection budget. Cloudflare allows 6 simultaneous outgoing connections per invocation
while waiting for headers (verified). Five lanes fits, with one slot spare, and only
during the header phase.

The SOCKS5 endpoints are the dead end regardless. `_dial` connects to
`127.0.0.1:<lane.socks_port>`. If the tor processes cannot exist (B1), the race has
nothing to race over. Verified by reading `mitm.py::_dial`.

**B5. A long-lived TLS connection to opencode.ai held across invocations.**

- Lambda: verified block. "Lambda freezes the execution environment when the runtime and
  each extension have completed and there are no pending events." A frozen TLS socket
  cannot carry the next request, and the environment is recycled every few hours.
- Azure: verified block for HTTP. "Regardless of the function app timeout setting, 230
  seconds is the maximum amount of time that an HTTP triggered function can take to
  respond to a request." The README records committed streams sitting at 400 to 460
  seconds of silence while the model thinks, measured 2026-10-16. That is over the cap
  before the model has said anything.
- Vercel: verified block. 1,800 s ceiling and a 4.5 MB response body cap. An SSE stream
  from a reasoning model exceeds both on a long answer.
- Cloudflare Workers: partially possible, and it is the interesting case. HTTP
  invocations have no duration limit while the client stays connected, and a Durable
  Object can hold an outbound `connect()` socket for as long as the DO lives. But
  module-scope sockets are forbidden, and the DO's TCP socket only keeps the DO alive
  and billed for 15 minutes per connection. This gets you a stateful holder, not a lane
  fleet.
- Cloud Run: possible inside one instance, up to the 60 minute request timeout. Again,
  that is part C, not serverless.

**B6. The session lock. Verified hard block on Cloudflare.**
`netutil.session_lock` needs `fcntl.flock` on POSIX or `msvcrt.locking` on Windows, on a
descriptor held for the process lifetime. Both `fcntl` and `msvcrt` are in Cloudflare's
"not available in Python Workers" list, and the filesystem is explicitly "not shared
between different isolate instances". On Lambda, /tmp is per execution environment, so
two concurrent Lambdas never see the same lock file. The lock would have to become a
DynamoDB conditional write, which is a different mechanism with different failure modes,
not a port. On every platform the semantics change: "one kitchen, one session" is local
machine mutual exclusion, and a distributed lease is not the same guarantee.

**B7. The proof window and the Windows Job Object. Local by construction.**
`proof.spawn_proof_window` calls `subprocess.Popen` with `CREATE_NEW_CONSOLE`, `wt`,
`gnome-terminal`, `konsole` or `xterm`. `winjob.ensure_kill_job` and `winjob.assign` are
ctypes calls into kernel32. Neither has a serverless analogue, and neither should.

### C. Correct alternative architecture for what cannot be serverless

Ranked by fit for this codebase, which is a long-lived multi-process supervisor with a
local socket server.

**C1. Cloud Run with min instances 1 and instance-based billing. The closest managed fit.**

Verified enablers: instance-based billing allocates CPU outside requests; minimum
instances keeps the instance alive past the 15 minute idle ceiling; SIGTERM gives 10
seconds to drain; maximum 8 vCPU and 32 GiB. Derived arithmetic from the published
us-central1 rates, which is a calculation and not a quoted figure: 1 vCPU plus 512 MiB
always on is 2,592,000 seconds times (0.000018 plus 0.5 times 0.000002), which is about
49 USD per month, less roughly 5 USD of monthly free tier credit, so about 44 USD per
month. That buys one vCPU for ten tor processes plus the relay, which is thin. Two vCPU
and 1 GiB is the realistic floor and roughly doubles it. Inference, from the code's own
note that a lane directory holds about 47 MB of downloaded state and from tor's typical
footprint. Google's own guidance for a single continuously running instance is the Cloud
Run instances resource, 7 days maximum before automatic restart, shared CPU at 6.25
percent baseline with bursting, which is cheaper than a service with minimum instances
and is explicitly recommended for "personal AI agents, stateful workflow engines, and
remote development environments".

**C2. Fly.io container with a volume. Cheapest verified always-on with persistent disk.**

shared-cpu-2x at 2 GB for 13.39 USD per month, plus a 1 GB volume at 0.15 USD per month,
plus egress at 0.02 USD per GB in North America and Europe. The lane state is about 47 MB
per lane by the code's own comment, so 10 lanes is about 470 MB, and a 1 GB volume holds
the consensus cache and the geoip file. No free tier; the trial is 2 hours of runtime.
Machines support Docker directly, so the port is a Dockerfile that installs tor and stem.

**C3. Render web service or background worker. Most managed, most expensive at parity.**

25 USD per month for 1 CPU and 2 GB, persistent disks at 0.25 USD per GB per month,
Docker support, zero downtime deploys, preview environments and private networking. You
pay roughly twice Fly for the operational surface.

**C4. Railway. Cheapest entry, usage metered.**

5 USD per month Hobby including 5 USD of usage, 20 USD per seat per month Pro. Good for a
prototype. The metering makes an always-on 10 tor fleet harder to predict than a flat
rate.

**C5. A VPS with a systemd service. Most control, least abstraction.**

VPS pricing was not fetched, so no number is quoted. The engineering point is that this
code ports unchanged: it is already a long-lived Python process that spawns children,
holds a listening socket and expects a filesystem. `Restart=always` replaces
HealthDaemon; `journalctl` replaces the proof log. You own patching, TLS termination and
the firewall.

**C6. Azure Functions Premium or Dedicated. Works, but is not serverless.**

Verified unbounded timeout and 3.5 to 14 GB on Premium. But you are paying for an App
Service plan, and the 230 second HTTP response cap still constrains any streaming client.

Do not use Lambda, Vercel Functions, Cloudflare Workers, or Azure Flex Consumption for
the lane fleet. Each fails on a specific verified constraint: environment recycling every
few hours, a 1,800 s ceiling, no process spawning in WASM, and a 230 second HTTP response
cap respectively.

One non-quota warning, stated as inference. The entire design exists to spread requests
across many exit IPs. Putting the fleet on one cloud host gives you ten Tor exits for the
data plane but one stable egress IP for everything else: the consensus fetch, DNS, the
update check. And a cloud VM's egress address is exactly the kind of stable, datacentre
attributed address that a free tier gate is most likely to refuse outright. The README's
own 403 FreeTierError story is about a client being refused, not an exit, so
concentrating the client behind one host address is the failure mode the lane design was
built to avoid.

### D. Hybrid: CLI stays local, coordination moves to serverless

This is the only split worth building, and it is small.

Move to serverless:

- The consensus fetch, parse and rank, as a scheduled job publishing a derived artefact:
  a ranked candidate list per country rather than the raw 10 MB consensus. `exits.claim`
  only needs `_open` to have a pool to sample from, and a few hundred ranked exits per
  country is enough for `EXIT_SAMPLE_K` of 12 to behave.
- The update manifest, already there.
- Optionally, proof event ingestion plus a web viewer.

Keep on the client:

- Everything stateful and every long-lived process: the tor fleet, the relay, the MITM
  CA, the proof window, the session lock.

What would have to be shared, and the consistency problems:

**D1. The consensus is about 10 MB and changes hourly.** The README already treats this
as a first class cost: "the only thing carried over besides that is tor's cached copy of
the public relay directory, because re-downloading it every launch turns a five-second
boot into a two-minute one." Shipping 10 MB per launch to every client reproduces that
cost. Shipping a derived shortlist fixes the size but changes the freshness semantics,
because a relay that goes bad between consensus refreshes stays pickable. The current code
already accepts that within a consensus epoch, so this is a widening of an existing
window, not a new class of bug. Inference, not a verified claim.

**D2. The notepad is a read-modify-write hot spot.** `bench.note_limited`, `note_spend`,
`note_verified` and `note_result` each read a JSON file, mutate it and write it back,
several times per request, from multiple threads, guarded only by a process local lock in
`proof.py` and per-lane locks in `lanes.py`. On a shared store every one of those becomes
a distributed read-modify-write. The counter shaped ones, `note_spend`, map cleanly onto
atomic increments. The max shaped ones, `note_limited`'s `until`, map onto a conditional
write. The day boundary roll, `_roll_spent`, `day_of` and `next_free_reset`, is a global
reset that needs either a TTL or a single owner, and getting it wrong silently resurrects
yesterday's walls or drops today's. Verified by reading `bench.py`; the distributed
failure modes are inference.

**D3. Exit stamps and lane pins must not be shared.** `used-exits.json` and
`verified-exits.json` exist so this user does not reuse a relay it just burnt. Sharing
them across users makes every user avoid what every other user just used, and the pool
collapses. There is a real argument for sharing `exit-spend.json`, because the free tier
meters per exit IP and two users on one address share one allowance, but publishing which
exits a user burnt is a privacy leak and a write amplification problem at the same time.
Recommendation: keep used, verified and spent local; share only the ranked candidate list
and the country scores, and treat the scores as a weak prior rather than truth. Inference.

**D4. The session lock does not translate, and does not need to.** It is local machine
mutual exclusion. In the hybrid it stays exactly where it is. Verified by reading
`netutil.py`.

**D5. The proof log does not translate unless the pane becomes a web page**, which
changes what the pane is for.

### E. Does the Vercel function pattern generalise, and what would it cost to run the whole thing that way?

It generalises cleanly to the parts in A, and the cost there is effectively nil. The
manifest already runs on Vercel's free Hobby tier with a 5 minute CDN cache. A consensus
rank endpoint and a notepad read endpoint are the same shape: stdlib Python, one handler,
cached at the edge.

Running the whole thing that way is not possible, and the specific reason is duration plus
ingress. The lane fleet needs a process that lives for hours, and Vercel Functions cap at
300 s on Hobby, 800 s on Pro, and 1,800 s on Pro and Enterprise in the beta. Even the
extended beta ceiling is half an hour. The client needs to reach the proxy, and Vercel
Functions are HTTPS only behind the edge, so they cannot terminate a connection from
127.0.0.1 on a laptop. The 4.5 MB body cap and the 1,800 s ceiling are both wrong for an
SSE stream from a reasoning model.

Vercel Daemons are the interesting near miss. They are container based, long running,
restart on crash, SIGTERM with configurable grace to 3,600 s, up to 100 instances per
region, and they run on all plans including Hobby. A daemon could run the ten tor
processes, because it is a container and containers can spawn children. But the verified
limits close the door:

- "Inbound HTTP or TCP traffic" is not supported. So the daemon cannot be the proxy
  endpoint. You would need a Vercel Function or Service in front of it, which
  reintroduces the duration and body caps on exactly the connection that must not have
  them.
- "Persistent local storage" is not supported. The Tor consensus cache, the geoip file
  and the five ledgers would have to live in Vercel Blob or a Marketplace database, which
  is a re-architecture of `bench.py` and `lanes.py`, not a port.
- Production only, no autoscaling, linux amd64, max 50 daemon instances per project
  environment.

Cost, as far as it was verified: the Pro quota is 16 vCPUs and 32 GiB running at once, so
ten 2 GiB and 1 vCPU daemons, one per lane, fit inside it with room to spare. Hobby's
quota is 5 Active CPU-hours per month, which a mostly idle daemon might survive since
waiting does not count as Active CPU, though HTTPS cipher operations do count, and this
workload is almost entirely HTTPS. Vercel's per unit Active CPU and Provisioned Memory
rates were not fetched, so no monthly figure is quoted. That number is on
vercel.com/pricing and should be checked before anyone commits.

---

## 4. Final recommendation

Do not migrate the lane engine to any function platform. The blocking constraints are
structural, not tunable: the tor fleet needs a supervised process that outlives every
documented invocation ceiling, the proxy needs to listen on 127.0.0.1 on the user's
machine, and the MITM needs the CA key to stay on that machine.

- Cloudflare Workers is the hardest no, because there is no process model at all.
- Azure Flex Consumption and Vercel Functions are closed by the 230 second HTTP response
  cap and the 1,800 second ceiling respectively.
- Lambda is closed by environment freezing and recycling.
- Cloud Run with min instances 1 and instance-based billing technically works and is the
  only function product that does, but at that point you are paying container prices for a
  container, and Google's own docs steer you to the Cloud Run instances resource instead.

Split the work instead. Move to serverless only the three things that are genuinely
stateless and short:

1. The update manifest, which is already there and already correct.
2. The hourly consensus fetch, parse and rank job, publishing a derived ranked shortlist
   per country rather than the raw 10 MB file.
3. Optionally proof event ingestion with a web viewer.

Keep everything else on the client: the tor fleet, the relay, the MITM CA, the proof
window, the session lock, and all five ledgers.

If the goal is to get the lane fleet off the user's laptop, the cheapest verified
always-on option is a Fly.io shared-cpu-2x machine with a 1 GB volume, at about 13.54 USD
per month plus egress, running the existing Python almost unchanged behind a Dockerfile.
The cheapest fully self-hosted option is any small VPS with a systemd unit, where
`Restart=always` replaces HealthDaemon and `journalctl` replaces the proof log. Prefer
Fly.io or a VPS over Render or Railway here: Render costs roughly twice as much at parity,
and Railway's usage metering makes an always-on ten-tor fleet hard to predict.

Before building any of it, price the two numbers that could not be verified: Vercel's
daemon unit rates on vercel.com/pricing, and a VPS provider's monthly rate. And weigh the
non-quota risk: concentrating the client behind one cloud egress address is the exact
failure mode the lane design exists to avoid.
