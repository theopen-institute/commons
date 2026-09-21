### Commons

Shared tools for Frappe

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app commons
```

#### Optional apps

This app requires nothing but Frappe. Two of its sections need another app, and
a site without that app gets this one without the section rather than not at
all — the endpoints behind it refuse and its rows leave the navigation.

| Section | Needs |
| --- | --- |
| Leave, Expense Claims | `hrms` |
| Procurement, Department Budgets | `erpnext` |

Install either alongside, in any order, and run `bench --site <site> migrate`.
Self-service, announcements, workspaces and the permission gate need neither.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/commons
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

none
