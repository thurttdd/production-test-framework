# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""InferenceX benchmark workload: runs benchmark_serving inside an existing Docker container via ``docker exec``."""

import logging
import threading
import time
from concurrent.futures import CancelledError, Future
from typing import Optional, Tuple

from ..helper import run_cancellable_command
from .workload import Workload, WorkloadResult, WorkloadStatus


class BenchmarkCancelled(Exception):
    """The benchmark run was terminated via :meth:`InferencexWorkload.stop`."""


class InferencexWorkload(Workload):
    """
    Run the InferenceX / vLLM ``benchmark_serving.py`` workload inside a container that is
    already running on the same host (requires ``docker`` on PATH; often used with a
    mounted Docker socket).

    The image must provide ``benchmark_script`` at the given path; adjust defaults to match
    your InferenceX container layout. The vLLM server is reached at ``vllm_host`` and
    ``vllm_port`` on the compose/stack network (e.g. service name or ``localhost``).
    """

    def __init__(
        self,
        *,
        image_name: str = "openmosaic/inferencex:latest",
        container_name: str = "inferencex",
        vllm_host: str = "localhost",
        vllm_port: int = 8080,
        benchmark_script: str = "/workspace/InferenceX/utils/bench_serving/benchmark_serving.py",
        python_executable: str = "python3",
        model: str = "Qwen/Qwen3-8B",
        backend: str = "vllm",
        dataset_name: str = "random",
        benchmark_extra_args: Tuple[str, ...] = (),
        docker_exec_timeout: float = 600.0
    ):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._result = ""
        self._completion_fut: Future | None = None
        self._cancel_event = threading.Event()

        self._container_name = container_name
        self._image_name = image_name
        self._vllm_host = vllm_host
        self._vllm_port = vllm_port
        self._benchmark_script = benchmark_script
        self._python_executable = python_executable
        self._model = model
        self._backend = backend
        self._dataset_name = dataset_name
        self._benchmark_extra_args = benchmark_extra_args
        self._docker_exec_timeout = docker_exec_timeout

    def _benchmark_inner_argv(self) -> list[str]:
        inner: list[str] = [
            self._python_executable,
            self._benchmark_script,
        ]
        inner.extend(
            [
                "--host",
                self._vllm_host,
                "--port",
                str(self._vllm_port),
                "--model",
                self._model,
                "--backend",
                self._backend,
                "--dataset-name",
                self._dataset_name,
            ]
        )
        inner.extend(self._benchmark_extra_args)
        return inner

    def _docker_exec_cmd(self) -> list[str]:
        return ["sudo", "docker", "run", "--rm", "-t", "--network", "host", "--name", self._container_name, self._image_name, *self._benchmark_inner_argv()]
        self._logger.info("Running: %s", " ".join(cmd))

    def start(self):
        self.logger.info("Starting inferencex workload")
        self._cancel_event.clear()
        with self._lock:
            self._start_time = time.time()
            self._workload_status = WorkloadStatus.RUNNING
            self._result = ""
        fut = self.submit_background(self._run_benchmark_sync)
        fut.add_done_callback(self._on_benchmark_done)
        with self._lock:
            self._completion_fut = fut

    def _run_benchmark_sync(self) -> str:
        cmd = self._docker_exec_cmd()
        self.logger.info("Running: %s", " ".join(cmd))
        result = run_cancellable_command(
            cmd,
            timeout=self._docker_exec_timeout,
            cancel_event=self._cancel_event,
            poll_interval=0.5,
        )
        if not result.success:
            if self._cancel_event.is_set():
                raise BenchmarkCancelled()
            raise RuntimeError(result.stderr or result.stdout or "benchmark failed")
        return result.stdout or "(no stdout)"

    def _on_benchmark_done(self, fut: Future) -> None:
        try:
            result = fut.result()
        except BenchmarkCancelled:
            self.logger.info("Inferencex benchmark stopped")
            with self._lock:
                self._workload_status = WorkloadStatus.STOPPED
                self._result = ""
            return
        except CancelledError:
            self.logger.info("Inferencex workload cancelled")
            with self._lock:
                self._workload_status = WorkloadStatus.STOPPED
            return
        except Exception as e:
            self.logger.exception("Inferencex benchmark failed")
            with self._lock:
                self._workload_status = WorkloadStatus.ERROR
                self._result = str(e)
            return
        finally:
            self._end_time = time.time()
        with self._lock:
            self._result = result
            self._workload_status = WorkloadStatus.COMPLETED

    def stop(self):
        self.logger.info("Stopping inferencex workload")
        self._cancel_event.set()
        with self._lock:
            fut = self._completion_fut
        if fut is not None:
            fut.cancel()
        with self._lock:
            self._workload_status = WorkloadStatus.STOPPED
            self._completion_fut = None

    def get_result(self) -> WorkloadResult:
        with self._lock:
            result = self._result
        return WorkloadResult(start_time=self._start_time, end_time=self._end_time, result=result, status=self.status)
