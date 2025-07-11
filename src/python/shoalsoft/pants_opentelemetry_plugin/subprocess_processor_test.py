# Copyright (C) 2025 Shoal Software LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import datetime
import tempfile

import pytest

from shoalsoft.pants_opentelemetry_plugin.message_protocol import OtelParameters
from shoalsoft.pants_opentelemetry_plugin.processor import IncompleteWorkunit, Level, Workunit
from shoalsoft.pants_opentelemetry_plugin.subprocess_processor import SubprocessProcessor


class MockProcessorContext:
    """Mock processor context for testing."""

    def __init__(self, metrics=None):
        self._metrics = metrics or {"test_metric": 42}

    def get_metrics(self):
        return self._metrics


def create_test_otel_parameters():
    """Create test OTel parameters for subprocess initialization."""
    return OtelParameters(
        endpoint="http://localhost:4318/v1/traces",
        certificate_file=None,
        client_key_file=None,
        client_certificate_file=None,
        headers={},
        timeout=30,
        compression=None,
        insecure=None,
    )


def test_subprocess_processor_initialization():
    """Test that SubprocessProcessor can be initialized with OTel
    parameters."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Verify initial state
    assert processor._otel_parameters == otel_params
    assert processor._build_root == "/tmp/test"
    assert processor._traceparent_env_var is None
    assert processor.subprocess is None
    assert not processor.initialized
    assert not processor.is_shutdown()


def test_subprocess_processor_lifecycle():
    """Test the basic lifecycle of SubprocessProcessor without full subprocess
    testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        otel_params = create_test_otel_parameters()
        processor = SubprocessProcessor(
            otel_parameters=otel_params,
            build_root=temp_dir,
            traceparent_env_var=None,
        )

        # Test initial state
        assert not processor.initialized
        assert processor.subprocess is None
        assert not processor.is_shutdown()

        # Note: We skip actual subprocess initialization to avoid test complexity
        # and focus on testing the processor's state management


def test_subprocess_processor_error_handling():
    """Test error handling in SubprocessProcessor."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Test operations before initialization
    context = MockProcessorContext()

    incomplete_workunit = IncompleteWorkunit(
        name="test_workunit",
        span_id="test_span_123",
        parent_ids=(),
        level=Level.INFO,
        description="Test workunit description",
        start_time=datetime.datetime.now(datetime.timezone.utc),
    )

    # These should not crash but should be no-ops
    processor.start_workunit(incomplete_workunit, context=context)

    from pants.util.frozendict import FrozenDict

    complete_workunit = Workunit(
        name="test_workunit",
        span_id="test_span_123",
        parent_ids=(),
        level=Level.INFO,
        description="Test workunit description",
        start_time=datetime.datetime.now(datetime.timezone.utc),
        end_time=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1),
        metadata=FrozenDict({}),
    )

    processor.complete_workunit(complete_workunit, context=context)
    processor.finish(timeout=datetime.timedelta(seconds=1), context=context)


def test_subprocess_processor_shutdown_monitoring():
    """Test shutdown monitoring functionality."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Initially not shutdown
    assert not processor.is_shutdown()

    # Test direct shutdown event setting
    processor._shutdown_event.set()
    assert processor.is_shutdown()

    # Test reset
    processor._shutdown_event.clear()
    assert not processor.is_shutdown()


def test_subprocess_processor_sequence_ids():
    """Test that sequence IDs are generated correctly."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Test sequence ID generation
    seq_id_1 = processor._get_next_sequence_id()
    seq_id_2 = processor._get_next_sequence_id()
    seq_id_3 = processor._get_next_sequence_id()

    assert seq_id_1 == 1
    assert seq_id_2 == 2
    assert seq_id_3 == 3


def test_subprocess_processor_message_creation():
    """Test message creation without subprocess initialization."""
    otel_params = create_test_otel_parameters()
    _ = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Test creating messages without initializing
    context = MockProcessorContext()

    # Create a message manually to test serialization
    from shoalsoft.pants_opentelemetry_plugin.message_protocol import (
        InitializeData,
        ProcessorMessage,
        ProcessorOperation,
        StartWorkunitData,
    )

    # Test InitializeData creation
    init_data = InitializeData(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )
    init_message = ProcessorMessage(
        operation=ProcessorOperation.INITIALIZE, data=init_data, sequence_id=1
    )

    # Test that message can be created
    assert init_message.operation == ProcessorOperation.INITIALIZE
    assert init_message.sequence_id == 1
    assert isinstance(init_message.data, InitializeData)
    assert init_message.data.otel_parameters == otel_params

    # Test StartWorkunitData creation
    incomplete_workunit = IncompleteWorkunit(
        name="test_workunit",
        span_id="test_span_123",
        parent_ids=(),
        level=Level.INFO,
        description="Test workunit description",
        start_time=datetime.datetime.now(datetime.timezone.utc),
    )

    from pants.util.frozendict import FrozenDict

    workunit_data = StartWorkunitData(
        workunit=incomplete_workunit,
        context_metrics=FrozenDict(context.get_metrics()),
    )

    start_message = ProcessorMessage(
        operation=ProcessorOperation.START_WORKUNIT, data=workunit_data, sequence_id=2
    )

    assert start_message.operation == ProcessorOperation.START_WORKUNIT
    assert start_message.sequence_id == 2
    assert isinstance(start_message.data, StartWorkunitData)
    assert start_message.data.workunit.name == "test_workunit"


def test_subprocess_processor_sync_methods():
    """Test sync methods of SubprocessProcessor."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Test wait_for_shutdown without initialization
    # Should return False for timeout when not shutdown
    result = processor.wait_for_shutdown(timeout=0.1)
    assert result is False

    # Set shutdown manually to test True case
    processor._shutdown_event.set()
    result = processor.wait_for_shutdown(timeout=0.1)
    assert result is True


def test_subprocess_processor_with_invalid_build_root():
    """Test SubprocessProcessor with invalid build root."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/nonexistent/invalid/path",
        traceparent_env_var=None,
    )

    # Should be able to create the processor
    assert processor._build_root == "/nonexistent/invalid/path"
    assert not processor.initialized

    # Initialization might fail due to invalid path, but shouldn't crash
    # We'll skip this test since it would require full subprocess setup


def test_subprocess_processor_traceparent_env_var():
    """Test SubprocessProcessor with traceparent environment variable."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var="TRACE_PARENT",
    )

    # Should be able to create the processor
    assert processor._traceparent_env_var == "TRACE_PARENT"
    assert not processor.initialized


def test_subprocess_processor_thread_lifecycle():
    """Test the thread lifecycle in SubprocessProcessor."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Initially threads are not started
    assert processor._sequence_reader_thread is None
    assert processor._stderr_reader_thread is None

    # Test that threads are not running
    assert not processor.is_shutdown()


def test_subprocess_processor_sequence_id_increments():
    """Test that sequence IDs increment correctly."""
    otel_params = create_test_otel_parameters()
    processor = SubprocessProcessor(
        otel_parameters=otel_params,
        build_root="/tmp/test",
        traceparent_env_var=None,
    )

    # Test that sequence IDs start at 0 and increment
    assert processor._next_sequence_id == 0
    assert processor._last_processed_sequence_id == 0

    # Get sequence IDs
    seq1 = processor._get_next_sequence_id()
    seq2 = processor._get_next_sequence_id()
    seq3 = processor._get_next_sequence_id()

    assert seq1 == 1
    assert seq2 == 2
    assert seq3 == 3
    assert processor._next_sequence_id == 3


def test_subprocess_server_argument_parsing():
    """Test that the subprocess server can parse all its defined arguments."""
    # Test basic argument parsing
    parser = argparse.ArgumentParser()
    OtelParameters.add_options_to_parser(parser)
    parser.add_argument("--build_root", default=None, action="store")
    parser.add_argument("--traceparent_env_var", default=None, action="store")

    # Test minimal arguments
    args = ["--build_root", "/tmp/test"]
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)

    assert parsed_options.build_root == "/tmp/test"
    assert parsed_options.traceparent_env_var is None
    assert otel_parameters.endpoint is None
    assert otel_parameters.insecure is None

    # Test all arguments
    args = [
        "--build_root",
        "/tmp/test",
        "--traceparent_env_var",
        "TRACE_PARENT",
        "--endpoint",
        "http://localhost:4318/v1/traces",
        "--certificate_file",
        "/path/to/cert.pem",
        "--client_key_file",
        "/path/to/key.pem",
        "--client_certificate_file",
        "/path/to/client.pem",
        "--headers",
        '{"x-api-key": "test"}',
        "--timeout",
        "30",
        "--compression",
        "gzip",
        "--insecure",
    ]
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)

    assert parsed_options.build_root == "/tmp/test"
    assert parsed_options.traceparent_env_var == "TRACE_PARENT"
    assert otel_parameters.endpoint == "http://localhost:4318/v1/traces"
    assert otel_parameters.certificate_file == "/path/to/cert.pem"
    assert otel_parameters.client_key_file == "/path/to/key.pem"
    assert otel_parameters.client_certificate_file == "/path/to/client.pem"
    assert otel_parameters.headers == {"x-api-key": "test"}
    assert otel_parameters.timeout == 30
    assert otel_parameters.compression == "gzip"
    assert otel_parameters.insecure is True

    # Test --no-insecure
    args = ["--build_root", "/tmp/test", "--no-insecure"]
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)

    assert otel_parameters.insecure is False


def test_subprocess_server_insecure_argument_variations():
    """Test that --insecure and --no-insecure arguments work correctly."""
    parser = argparse.ArgumentParser()
    OtelParameters.add_options_to_parser(parser)
    parser.add_argument("--build_root", default=None, action="store")

    # Test --insecure
    args = ["--build_root", "/tmp/test", "--insecure"]
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)
    assert otel_parameters.insecure is True

    # Test --no-insecure
    args = ["--build_root", "/tmp/test", "--no-insecure"]
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)
    assert otel_parameters.insecure is False

    # Test neither (default)
    args = ["--build_root", "/tmp/test"]
    parsed_options = parser.parse_args(args)
    otel_parameters = OtelParameters.from_parsed_options(parsed_options)
    assert otel_parameters.insecure is None


def test_subprocess_server_mutually_exclusive_insecure_args():
    """Test that --insecure and --no-insecure are mutually exclusive."""
    parser = argparse.ArgumentParser()
    OtelParameters.add_options_to_parser(parser)
    parser.add_argument("--build_root", default=None, action="store")

    # Test that using both --insecure and --no-insecure raises an error
    args = ["--build_root", "/tmp/test", "--insecure", "--no-insecure"]
    with pytest.raises(SystemExit):
        parser.parse_args(args)


def test_otel_parameters_to_args_for_subprocess():
    """Test that OtelParameters.to_args_for_subprocess() generates correct
    arguments."""
    # Test with insecure=True
    params = OtelParameters(
        endpoint="http://localhost:4318/v1/traces",
        certificate_file=None,
        client_key_file=None,
        client_certificate_file=None,
        headers={"x-api-key": "test"},
        timeout=30,
        compression="gzip",
        insecure=True,
    )
    args = params.to_args_for_subprocess()
    expected_args = [
        "--endpoint",
        "http://localhost:4318/v1/traces",
        "--headers",
        '{"x-api-key": "test"}',
        "--timeout",
        "30",
        "--compression",
        "gzip",
        "--insecure",
    ]
    assert args == expected_args

    # Test with insecure=False
    params = OtelParameters(
        endpoint="http://localhost:4318/v1/traces",
        certificate_file=None,
        client_key_file=None,
        client_certificate_file=None,
        headers=None,
        timeout=None,
        compression=None,
        insecure=False,
    )
    args = params.to_args_for_subprocess()
    expected_args = ["--endpoint", "http://localhost:4318/v1/traces", "--no-insecure"]
    assert args == expected_args

    # Test with insecure=None
    params = OtelParameters(
        endpoint="http://localhost:4318/v1/traces",
        certificate_file=None,
        client_key_file=None,
        client_certificate_file=None,
        headers=None,
        timeout=None,
        compression=None,
        insecure=None,
    )
    args = params.to_args_for_subprocess()
    expected_args = ["--endpoint", "http://localhost:4318/v1/traces"]
    assert args == expected_args


if __name__ == "__main__":
    pytest.main([__file__])
