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


if __name__ == "__main__":
    pytest.main([__file__])
