files(
    name="plugin_files_for_integration_test",
    sources=["shoalsoft/**/*.py", "shoalsoft/**/requirements.txt"],
)

__defaults__(
    {
        (python_sources, python_tests): {
            "resolve": parametrize("pants-2.24.x", "pants-2.23.x"),
        }
    }
)
