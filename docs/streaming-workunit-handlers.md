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