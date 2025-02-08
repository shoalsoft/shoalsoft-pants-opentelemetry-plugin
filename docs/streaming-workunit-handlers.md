# Streaming Workunit Handlers

## Overview

Pants uses an internal tracing format called "workunits" for tracing execution timing. Workunits are mostly equivalent to tracing spans in other systems. The engine supports "streaming workunit handlers" to process and send workunits to monitoring systems.

## Handler Setup

To setup a streaming workunit handler, plugins should do the following:

1. First, implement the [`WorkunitsCallbackFactoryRequest` union](https://github.com/pantsbuild/pants/blob/fecc16585d40e51cb42469ece320462d22ea25e2/src/python/pants/engine/streaming_workunit_handler.py#L203) with a rule
which returns a [`WorkunitsCallbackFactory`](https://github.com/pantsbuild/pants/blob/fecc16585d40e51cb42469ece320462d22ea25e2/src/python/pants/engine/streaming_workunit_handler.py#L188) so the engine can gather workunit handler callbacks.

2. The `WorkunitsCallbackFactory.callback_factory` when invoked should either return a [`WorkunitsCallback`](https://github.com/pantsbuild/pants/blob/fecc16585d40e51cb42469ece320462d22ea25e2/src/python/pants/engine/streaming_workunit_handler.py#L157), or else `None` if no handler should be activated.

3. The `WorkunitsCallback` can be any type which is callable and accepts the signature declared in the Pants source, and also implements a `can_finish_async` property which informs Pants whether Pants should wait or not for the callback to complete at the end of a run. The parameters passed to the callable are:

  - `started_workunits`: Workunits which were started.
  - `completed_workunits`: Workunits which completed.
  - `finished`: When `True`, the end of the session has been reached and the callback will not be invoked any more.
  - `context`: Useful context including access to the engine, and session-specific metrics like counters and observation histograms.

## Workunit Format

Workunits are untyped Python dictionaries and have the following structure:

<table>
    <tr>
        <th>Field</th>
        <th>Type</th>
        <th>Sample</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><code>name</code></td>
        <td>string</td>
        <td>`pants.backend.project_info.list_targets.list_targets`</td>
        <td>Name of the workunit.</td>
    </tr>
    <tr>
        <td><code>span_id</code></td>
        <td>string</td>
        <td><code>"56a74a32fdade07b"</code></td>
        <td>Unique identifider for this workunit.</td>
    </tr>
    <tr>
        <td><code>parent_ids</code></td>
        <td>list[string]</td>
        <td>['56a74a32fdade07b']</td>
        <td>List of the span IDs which are the parent(s) of this workunit in the tracing graph.</td>
    </tr>
    <tr>
        <td><code>level</code></td>
        <td>string (enum)</td>
        <td>DEBUG</td>
        <td>The logging level for this workunuit. One of ERROR, WARN, INFO, DEBUG, or TRACE.</td>
    </tr>
    <tr>
        <td><code>description</code></td>
        <td>string</td>
        <td>"`list` goal'"</td>
        <td>Human-readable description of the task represented by the workunit.</td>
    </tr>
    <tr>
        <td><code>start_secs</code></td>
        <td>integer</td>
        <td>1738032069</td>
        <td>Numer of seconds since the unix epoch UTC for the start of the workunit's execution.</td>
    </tr>
    <tr>
        <td><code>start_nanos</code></td>
        <td>integer</td>
        <td>440807186</td>
        <td>Sub-second nanoseconds comoponent of the workunit's start time.</td>
    </tr>
    <tr>
        <td><code>duration_secs</code></td>
        <td>integer</td>
        <td>0</td>
        <td>Seconds component of the duration of time during which this workunit executed. to compute the end time, add this value (along with `duration_nanos`) to the time represented by `start_secs` and `start_nanos`.</td>
    </tr>
    <tr>
        <td><code>duration_nanos</code></td>
        <td>integer</td>
        <td>18695352</td>
        <td>Sub-second nanoseconds component of the time during which this workunit executed.</td>
    </tr>
    <tr>
        <td><code>metadata</code></td>
        <td>object</td>
        <td>{}</td>
        <td>Workunit-specific mapping of metadata values. Metadata may be added by Pants rules to annonate a workunit's execution. (See the <a href="https://github.com/pantsbuild/pants/blob/1d1e93edcdf617c651c3eb1d1cbadd29d99172b2/src/python/pants/engine/engine_aware.py#L29">EngineAwareParameter.metadata</a> and <a href="https://github.com/pantsbuild/pants/blob/1d1e93edcdf617c651c3eb1d1cbadd29d99172b2/src/python/pants/engine/engine_aware.py#L82">EngineAwareReturnType.metadata</a> methods for more details.)</td>
    </tr>
    <tr>
        <td><code>artifacts</code></td>
        <td>object</td>
        <td>{}</td>
        <td>
            <p>Workunit-specific mapping of artifacts added by Pants rules to annotate workunit execution. (See the <a href="https://github.com/pantsbuild/pants/blob/1d1e93edcdf617c651c3eb1d1cbadd29d99172b2/src/python/pants/engine/engine_aware.py#L74">EngineAwareReturnType.artifacts</a> method for more details.)</p>
            <p>The mapping will be filled with the name of the artifact as the key and a value represening either a "file digest" or "digest snapshot" represented by the following instance classes:</p>
            <ul>
                <li><a href="https://github.com/pantsbuild/pants/blob/2c16710c62b7f0db59ee4b055e897a5cbc0e9d3f/src/python/pants/engine/internals/native_engine.pyi#L404"><code>FileDigest</code></a> with <code>fingerprint</code> and <code>serialized_bytes_length</code> properties</li>
                <li><a href="https://github.com/pantsbuild/pants/blob/2c16710c62b7f0db59ee4b055e897a5cbc0e9d3f/src/python/pants/engine/internals/native_engine.pyi#L416"><code>Snapshot</code></a> with <code>digest</code>, <code>dirs</code>, and <code>files</code> properties. <code>digest</code> has <code>fingerprint</code> and <code>serialized_bytes_length</code> properties.</li>
            </ul>
        </td>
    </tr>
    <tr>
        <td><code>counters</code></td>
        <td>object</td>
        <td>{}</td>
        <td><b>DEPRECATED</b>. This used to store the counters which were incremented during the execution of this partcular workunit. For various reasons, Pants does not track counter increments to workunuits any more here. Use the global counters for a session instead which can be obtaind from the <a href="https://github.com/pantsbuild/pants/blob/fecc16585d40e51cb42469ece320462d22ea25e2/src/python/pants/engine/streaming_workunit_handler.py#L92"><code>StreamingWorkunitContext.get_metrics</code</a> method.</td>
    </tr>
</table>

See the [`workunit_to_py_value` function](https://github.com/pantsbuild/pants/blob/f783ea5ced4ca559f3c82f70e0116c6c78892303/src/rust/engine/src/externs/interface.rs#L823) for details of how a Rust workunit value is exposed to Python rule code.

### Known Metadata

There is no specification currently for the metadata generated by Pants (besides the source code which is of course not an actual specification). This section has been derived empiracally by observing actual traces. Pants makes no promises not to change these schemas.

#### Process Metadata

This metadata appears on `process` spans:

<table>
    <tr>
        <th>Key</th>
        <th>Type</th>
        <th>Sample</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><code>definition</code></td>
        <td>object</td>
        <td>see below</td>
        <td>Process definiiton which was executed by Pants. See sample JSON below this table.</td>
    </tr>
    <tr>
        <td><code>environment_type</code></td>
        <td>string (enum)</td>
        <td>local</td>
        <td>The kind of environment in which the process executed (originally executed if cached). Valid values are `docker`, `local`, `remote`, and `workspace` corresponding to the `docker_environment`, `local_environment`, `remote_environment`, and `experimental_workspace_environment` target types, respectively.</td>
    </tr>
    <tr>
        <td><code>exit_code</code></td>
        <td>int</td>
        <td>0</td>
        <td>Exit code of the process execution</td>
    </tr>
    <tr>
        <td><code>saved_by_cache_ms</code></td>
        <td>int</td>
        <td>62</td>
        <td>Time saved by using a cache over re-executing this process (if this process was cached) in milliseconds.</td>
    </tr>
    <tr>
        <td><code>source</code></td>
        <td>string (enum)</td>
        <td>HitLocally</td>
        <td>
            <p>Represents whether process was actually run or was cached. Valid values:</p>
            <ul>
                <li><code>Ran</code>: The process was actually executed.</li>
                <li><code>HitLocally</code>: The process output was cached locally.</li>
                <li><code>HitRemotely</code>: The process output was cached remotely.</li>
            </ul>
        </td>
    </tr>
    <tr>
        <td><code>total_elapsed_ms</code></td>
        <td>int</td>
        <td>100</td>
        <td>Total time to execute the process originally in milliseconds.</td>
    </tr>
</table>

Sample JSON for the process definition (as of Pants 2.24.x):

```
{
    "argv": [
        "__coursier/coursier_post_process_stderr.py",
        "/bin/bash",
        "__coursier/coursier_fetch_wrapper_script.sh",
        "__coursier/./cs-x86_64-apple-darwin",
        "coursier_report.json",
        "--intransitive",
        "com.lihaoyi:sourcecode_2.13:0.3.0"
    ],
    "env": {
        "COURSIER_ARCHIVE_CACHE": ".cache/arc",
        "COURSIER_CACHE": ".cache/82ce2b8f4bc8f448df4f6ed5355885af1faeecda677ab193fad51e95d47d1677/jdk",
        "COURSIER_JVM_CACHE": ".cache/v1"
    },
    "working_directory": null,
    "input_digests": {
        "complete": {
            "digest": {
                "fingerprint": "2c6a51e70e246e42a6242160a954e8c54d9c35b9ec6dc6baa9fa7748ae8e95ed",
                "size_bytes": 85
            }
        },
        "nailgun": {
            "digest": {
                "fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size_bytes": 0
            }
        },
        "inputs": {
            "digest": {
                "fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size_bytes": 0
            }
        },
        "immutable_inputs": {
            "__coursier": {
                "digest": {
                    "fingerprint": "8c70f32ac92ed8ac5c7471940f415b6f9194a8a1bf5ea6a781d1a37236f115f2",
                    "size_bytes": 429
                }
            }
        },
        "use_nailgun": []
    },
    "output_files": [
        "coursier_report.json"
    ],
    "output_directories": [
        "classpath"
    ],
    "timeout": null,
    "execution_slot_variable": null,
    "concurrency_available": 0,
    "description": "Fetching with coursier: com.lihaoyi:sourcecode_2.13:0.3.0",
    "level": "DEBUG",
    "append_only_caches": {
        "coursier": ".cache",
        "python_build_standalone": ".python-build-standalone"
    },
    "jdk_home": null,
    "cache_scope": "Successful",
    "execution_environment": {
        "name": null,
        "platform": "Macos_x86_64",
        "strategy": "Local"
    },
    "remote_cache_speculation_delay": {
        "secs": 0,
        "nanos": 0
    },
    "attempt": 0
}
```