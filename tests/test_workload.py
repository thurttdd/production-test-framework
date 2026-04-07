# SPDX-License-Identifier: FSL-1.1-ALv2
# Copyright (c) 2025 Delos Data, Inc.

"""Unit tests for workload base and concrete workload classes."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from production_test_framework.ssh import CommandResult
from production_test_framework.vllm import InferenceResult
from production_test_framework.workload.inferencex_workload import InferencexWorkload
from production_test_framework.workload.prompt_workload import BACKEND_TYPE, PromptWorkload
from production_test_framework.workload.workload import Workload, WorkloadStatus


class TestWorkloadStatus:
    """Tests for WorkloadStatus enum."""

    def test_member_values(self):
        assert WorkloadStatus.RUNNING.value == "running"
        assert WorkloadStatus.STOPPED.value == "stopped"
        assert WorkloadStatus.COMPLETED.value == "completed"
        assert WorkloadStatus.ERROR.value == "error"


class TestWorkload:
    """Tests for abstract Workload base class."""

    def test_cannot_instantiate_abstract_workload(self):
        with pytest.raises(TypeError, match="abstract"):
            Workload()

    def test_wait_for_completion_returns_true_when_predicate_succeeds(self):
        class CompletingWorkload(Workload):
            def __init__(self):
                super().__init__()

            def start(self):
                self._workload_status = WorkloadStatus.RUNNING

                def finish():
                    self._workload_status = WorkloadStatus.COMPLETED

                self.submit_background(finish)

            def stop(self):
                self._workload_status = WorkloadStatus.STOPPED

            def get_result(self) -> str:
                return "done"

        with patch(
            "production_test_framework.workload.workload.wait_for",
            return_value=True,
        ) as mock_wait:
            wl = CompletingWorkload()
            assert wl.wait_for_completion(timeout=10.0, poll_interval=1.0) is True

        mock_wait.assert_called_once()
        args, kwargs = mock_wait.call_args
        assert kwargs == {}
        pred, timeout_arg, poll_arg = args
        assert timeout_arg == 10.0
        assert poll_arg == 1.0
        wl._workload_status = WorkloadStatus.COMPLETED
        assert pred() is True

    def test_wait_for_completion_returns_false_when_wait_times_out(self):
        class NeverCompletingWorkload(Workload):
            def __init__(self):
                super().__init__()
                self._workload_status = WorkloadStatus.RUNNING

            def start(self):
                pass

            def stop(self):
                pass

            def get_result(self) -> str:
                return ""

        with patch(
            "production_test_framework.workload.workload.wait_for",
            return_value=False,
        ) as mock_wait:
            wl = NeverCompletingWorkload()
            assert wl.wait_for_completion(timeout=5.0, poll_interval=1.0) is False

        mock_wait.assert_called_once()

    def test_status_property_reads_workload_status(self):
        class DummyWorkload(Workload):
            def start(self):
                pass

            def stop(self):
                pass

            def get_result(self) -> str:
                return ""

        w = DummyWorkload()
        assert w.status == WorkloadStatus.STOPPED
        w._workload_status = WorkloadStatus.RUNNING
        assert w.status == WorkloadStatus.RUNNING

    def test_submit_background_runs_callable(self):
        class RunnableWorkload(Workload):
            def __init__(self):
                super().__init__()
                self.seen = []

            def start(self):
                pass

            def stop(self):
                pass

            def get_result(self) -> str:
                return ""

            def capture(self, x):
                self.seen.append(x)

        w = RunnableWorkload()
        try:
            fut = w.submit_background(w.capture, 42)
            assert fut.result(timeout=5.0) is None
            assert w.seen == [42]
        finally:
            w.shutdown_executor(wait=True)


class TestInferencexWorkload:
    """Tests for Inferencex workload."""

    @pytest.fixture
    def mock_inferencex_run(self):
        with patch(
            "production_test_framework.workload.inferencex_workload.run_cancellable_command",
        ) as m:
            m.return_value = CommandResult(
                returncode=0,
                stdout="benchmark output\n",
                stderr="",
            )
            yield m

    def test_is_workload_subclass(self):
        assert issubclass(InferencexWorkload, Workload)

    def test_can_instantiate(self):
        w = InferencexWorkload()
        assert isinstance(w, Workload)

    def test_initial_status_is_stopped(self):
        w = InferencexWorkload()
        assert w.status == WorkloadStatus.STOPPED

    def test_start_transitions_to_running(self, mock_inferencex_run):
        w = InferencexWorkload()
        w.start()
        assert w.status in (WorkloadStatus.RUNNING, WorkloadStatus.COMPLETED)
        w.shutdown_executor(wait=True, cancel_futures=True)

    def test_stop_returns_to_stopped(self, mock_inferencex_run):
        w = InferencexWorkload()
        w.start()
        w.stop()
        assert w.status == WorkloadStatus.STOPPED
        _args, kwargs = mock_inferencex_run.call_args
        assert kwargs["cancel_event"].is_set()
        w.shutdown_executor(wait=True)

    def test_get_result_after_completion(self, mock_inferencex_run):
        w = InferencexWorkload()
        w.start()
        fut = w._completion_fut
        assert fut is not None
        fut.result(timeout=10.0)
        assert w.status == WorkloadStatus.COMPLETED
        assert w.get_result().result == "benchmark output\n"
        assert w.get_result().status == WorkloadStatus.COMPLETED
        assert w.get_result().start_time is not None
        assert w.get_result().end_time is not None
        assert w.get_result().runtime is not None
        w.shutdown_executor(wait=True)

    def test_docker_exec_argv_includes_container_host_port(self, mock_inferencex_run):
        w = InferencexWorkload(
            container_name="mycontainer",
            vllm_host="vllm.svc",
            vllm_port=9090,
        )
        w.start()
        w._completion_fut.result(timeout=10.0)
        cmd = mock_inferencex_run.call_args[0][0]
        assert cmd[:3] == ["sudo", "docker", "run"]
        assert "--host" in cmd
        assert "vllm.svc" in cmd
        assert "--port" in cmd
        assert "9090" in cmd
        assert "--base-url" not in cmd
        w.shutdown_executor(wait=True)

    def test_stop_while_running_sets_cancel_on_mock(self, mock_inferencex_run):
        def run_until_cancel(cmd, *, timeout, cancel_event, **kwargs):
            for _ in range(500):
                if cancel_event.is_set():
                    return CommandResult(returncode=-1, stdout="", stderr="cancelled")
                time.sleep(0.01)
            return CommandResult(returncode=0, stdout="done", stderr="")

        mock_inferencex_run.side_effect = run_until_cancel
        w = InferencexWorkload()
        w.start()
        time.sleep(0.05)
        w.stop()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if w.status == WorkloadStatus.STOPPED and w.get_result() == "":
                break
            time.sleep(0.02)
        assert w.status == WorkloadStatus.STOPPED
        assert w.get_result().result == ""
        assert w.get_result().status == WorkloadStatus.STOPPED
        assert w.get_result().start_time is not None
        assert w.get_result().end_time is not None
        assert w.get_result().runtime is not None
        w.shutdown_executor(wait=True)

    def test_second_start_raises_when_already_running(self, mock_inferencex_run):
        block = threading.Event()

        def slow_run(*_args, **_kwargs):
            block.wait(timeout=60.0)
            return CommandResult(returncode=0, stdout="done", stderr="")

        mock_inferencex_run.side_effect = slow_run
        w = InferencexWorkload()
        w.start()
        assert w.status == WorkloadStatus.RUNNING
        with pytest.raises(
            RuntimeError,
            match="Inferencex workload already running",
        ):
            w.start()
        block.set()
        w._completion_fut.result(timeout=10.0)
        w.shutdown_executor(wait=True)


class TestPromptWorkload:
    """Tests for prompt-driven workload against a backend."""

    @pytest.fixture
    def mock_vllm_client_class(self):
        with patch(
            "production_test_framework.workload.prompt_workload.VllmClient",
        ) as m:
            backend = MagicMock()
            backend.wait_for_ready = MagicMock(return_value=True)
            backend.complete = MagicMock(
                return_value=InferenceResult(success=True, text="model output")
            )
            m.return_value = backend
            yield m, backend

    def test_default_backend_is_vllm(self, mock_vllm_client_class):
        mock_cls, backend = mock_vllm_client_class
        wl = PromptWorkload("hello world")
        mock_cls.assert_called()
        assert wl.prompt == "hello world"
        backend.wait_for_ready.assert_not_called()
        wl.shutdown_executor(wait=True)

    def test_passes_host_and_port_to_vllm_client(self, mock_vllm_client_class):
        mock_cls, _backend = mock_vllm_client_class
        wl = PromptWorkload(
            "q",
            backend_type=BACKEND_TYPE.VLLM,
            host="vllm.internal",
            port=9090,
        )
        mock_cls.assert_called()
        wl.shutdown_executor(wait=True)

    def test_start_waits_for_backend_and_dispatches_completion(self, mock_vllm_client_class):
        mock_cls, backend = mock_vllm_client_class
        wl = PromptWorkload("run this")
        wl.start()

        backend.wait_for_ready.assert_called_once_with(timeout=30)
        backend.complete.assert_called_once()
        fut = wl._completion_fut
        assert fut is not None
        fut.result(timeout=10.0)
        assert wl.status == WorkloadStatus.COMPLETED
        wl.shutdown_executor(wait=True)

    def test_stop_cancels_future(self, mock_vllm_client_class):
        _mock_cls, backend = mock_vllm_client_class
        wl = PromptWorkload("x")
        fake_fut = MagicMock()
        with patch.object(wl, "submit_background", return_value=fake_fut):
            wl.start()
            wl.stop()
        fake_fut.cancel.assert_called_once()
        assert wl.status == WorkloadStatus.STOPPED
        wl.shutdown_executor(wait=True)

    def test_get_result_returns_inference_text_after_completion(self, mock_vllm_client_class):
        mock_cls, backend = mock_vllm_client_class
        backend.complete = MagicMock(
            return_value=InferenceResult(success=True, text="final text")
        )
        wl = PromptWorkload("prompt")
        wl.start()
        wl._completion_fut.result(timeout=10.0)
        assert wl.status == WorkloadStatus.COMPLETED
        assert wl.get_result().result.text == "final text"
        assert wl.get_result().status == WorkloadStatus.COMPLETED
        assert wl.get_result().start_time is not None
        assert wl.get_result().end_time is not None
        assert wl.get_result().runtime is not None
        wl.shutdown_executor(wait=True)

    def test_second_start_raises_when_already_running(self, mock_vllm_client_class):
        _mock_cls, backend = mock_vllm_client_class
        block = threading.Event()

        def blocking_complete(_prompt):
            block.wait(timeout=60.0)
            return InferenceResult(success=True, text="ok")

        backend.complete = MagicMock(side_effect=blocking_complete)
        wl = PromptWorkload("x")
        wl.start()
        assert wl.status == WorkloadStatus.RUNNING
        with pytest.raises(
            RuntimeError,
            match="Prompt workload already running",
        ):
            wl.start()
        block.set()
        wl._completion_fut.result(timeout=10.0)
        wl.shutdown_executor(wait=True)
