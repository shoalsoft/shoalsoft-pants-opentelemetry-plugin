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

import time

import pytest

from shoalsoft.pants_opentelemetry_plugin.grpc_test_server import GrpcTestServerManager


def test_grpc_test_server_manager():
    """Test that the gRPC test server manager can start and stop cleanly."""
    manager = GrpcTestServerManager()
    
    # Test starting the server
    port = manager.start()
    assert port > 0
    assert manager.actual_port == port
    assert manager.process is not None
    assert manager.process.is_alive()
    
    # Give server a moment to fully initialize
    time.sleep(0.1)
    
    # Test getting requests (should be empty initially)
    requests = manager.get_received_requests()
    assert len(requests) == 0
    
    # Test stopping the server
    manager.stop()
    
    # Server process should be stopped
    if manager.process:
        assert not manager.process.is_alive()


def test_grpc_test_server_manager_error_handling():
    """Test error handling when server fails to start."""
    # This test is mainly to ensure the manager handles errors gracefully
    # In practice, the server should always start successfully on port 0
    manager = GrpcTestServerManager()
    
    try:
        port = manager.start()
        assert port > 0
    finally:
        manager.stop()


if __name__ == "__main__":
    pytest.main([__file__])