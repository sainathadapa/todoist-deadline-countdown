# Deadline Existence Query Design

## Goal

Fetch every active Todoist task that has a deadline without imposing an arbitrary future-date boundary.

## Design

`TodoistClient.list_deadlined_tasks()` will call Todoist's filter endpoint with the query `!no deadline` instead of `deadline before: 5 years from now`.

The change will not add project exclusions, environment variables, configuration, or client-side filtering. Existing pagination flattening and retry behavior remain unchanged.

## Testing

The existing client unit test will assert that `filter_tasks()` receives `query="!no deadline"` and that paginated results are still flattened. The targeted client test and complete test suite will be run after implementation.
