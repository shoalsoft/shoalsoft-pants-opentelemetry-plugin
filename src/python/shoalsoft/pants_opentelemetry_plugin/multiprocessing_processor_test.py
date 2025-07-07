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
from pathlib import Path
from unittest.mock import Mock

import pytest

from shoalsoft.pants_opentelemetry_plugin.multiprocessing_processor import MultiprocessingProcessor
from shoalsoft.pants_opentelemetry_plugin.processor import IncompleteWorkunit, Level, Workunit
from shoalsoft.pants_opentelemetry_plugin.register import (
    ProcessorFactoryData,
    _create_otel_processor,
    _serialize_telemetry_config,
)
from shoalsoft.pants_opentelemetry_plugin.subsystem import TracingExporterId


def test_multiprocessing_processor_basic_functionality():
    """Test that the multiprocessing processor can be created and cleaned
    up."""
    # Create a mock telemetry subsystem
    telemetry = Mock()
    telemetry.enabled = True
    telemetry.exporter = TracingExporterId.JSON_FILE
    telemetry.exporter_endpoint = None
    telemetry.exporter_headers = {}
    telemetry.exporter_timeout = 30
    telemetry.exporter_compression = Mock()
    telemetry.exporter_compression.value = "none"
    telemetry.exporter_insecure = False
    telemetry.exporter_certificate_file = None
    telemetry.exporter_client_key_file = None
    telemetry.exporter_client_certificate_file = None
    telemetry.json_file = "test.json"
    telemetry.parse_traceparent = False
    telemetry.finish_timeout = 10
    telemetry.async_completion = False

    with tempfile.TemporaryDirectory() as temp_dir:
        build_root = Path(temp_dir)

        # Create factory data using dataclass
        factory_data = ProcessorFactoryData(
            span_exporter_name=TracingExporterId.JSON_FILE,
            build_root=build_root,
            traceparent_env_var=None,
            telemetry_config=_serialize_telemetry_config(telemetry),
        )

        processor = MultiprocessingProcessor(
            processor_factory=_create_otel_processor,
            processor_factory_data=factory_data,
        )

        # Test initialization
        processor.initialize()
        assert processor._initialized
        assert processor._subprocess is not None
        assert processor._subprocess.is_alive()

        # Test workunit operations
        context = Mock()
        context.get_metrics.return_value = {"test_metric": 42}

        incomplete_workunit = IncompleteWorkunit(
            name="test_workunit",
            span_id="test_span_id",
            parent_ids=(),
            level=Level.INFO,
            description="Test workunit",
            start_time=datetime.datetime.now(datetime.timezone.utc),
        )

        # This should not raise an exception
        processor.start_workunit(incomplete_workunit, context=context)

        complete_workunit = Workunit(
            name="test_workunit",
            span_id="test_span_id",
            parent_ids=(),
            level=Level.INFO,
            description="Test workunit",
            start_time=datetime.datetime.now(datetime.timezone.utc),
            end_time=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=1),
            metadata={},
        )

        # This should not raise an exception
        processor.complete_workunit(complete_workunit, context=context)

        # Test finish
        processor.finish(timeout=datetime.timedelta(seconds=5), context=context)

        # Subprocess should be cleaned up
        assert not processor._subprocess.is_alive()


def test_multiprocessing_processor_error_handling():
    """Test error handling when subprocess fails to start."""
    telemetry = Mock()
    telemetry.enabled = True
    # Use invalid configuration to trigger errors
    telemetry.json_file = None  # This should cause an error

    with tempfile.TemporaryDirectory() as temp_dir:
        build_root = Path(temp_dir)

        # Create factory data using dataclass
        factory_data = ProcessorFactoryData(
            span_exporter_name=TracingExporterId.JSON_FILE,
            build_root=build_root,
            traceparent_env_var=None,
            telemetry_config=_serialize_telemetry_config(telemetry),
        )

        processor = MultiprocessingProcessor(
            processor_factory=_create_otel_processor,
            processor_factory_data=factory_data,
        )

        # Initialization should handle errors gracefully
        with pytest.raises(RuntimeError, match="Subprocess initialization"):
            processor.initialize()


if __name__ == "__main__":
    pytest.main([__file__])
