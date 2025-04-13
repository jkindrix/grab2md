"""
Command-line interface for managing the html2md configuration file.
"""

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from html2md.config.loader import CONFIG_FILE, load_config

# Create Rich console for beautiful output
console = Console()

# Create Typer app
app = typer.Typer(
    help="Manage html2md configuration settings.",
    add_completion=False,
)


@app.command(name="show")
def show_config():
    """Display the current configuration."""
    config = load_config()
    config_path = CONFIG_FILE

    # Display config path
    console.print(f"[bold blue]Configuration file:[/bold blue] {config_path}")

    # Display config as syntax-highlighted JSON
    json_str = json.dumps(config, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)

    console.print(Panel(syntax, title="Current Configuration", border_style="green"))


@app.command(name="path")
def show_config_path():
    """Show the path to the configuration file."""
    console.print(f"[bold green]Configuration file:[/bold green] {CONFIG_FILE}")


@app.command(name="set")
def set_config_value(
    path: str = typer.Argument(
        ..., help="Config path (e.g., 'domains.example.com.footer_marker')"
    ),
    value: str = typer.Argument(..., help="Value to set"),
):
    """Set a configuration value at the specified path."""
    config = load_config()

    # Split the path into components
    components = path.split(".")

    # Navigate to the destination
    current = config
    for i, component in enumerate(components[:-1]):
        if component not in current:
            # Create missing dictionaries along the path
            current[component] = {}
        elif not isinstance(current[component], dict):
            console.print(
                f"[bold red]Error:[/bold red] '{'.'.join(components[:i+1])}' is not a dictionary"
            )
            return
        current = current[component]

    # Set the value (convert to appropriate type if possible)
    last_component = components[-1]
    try:
        # Try to parse as JSON
        parsed_value = json.loads(value)
        current[last_component] = parsed_value
    except json.JSONDecodeError:
        # If not valid JSON, use as string
        current[last_component] = value

    # Save the updated config
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    console.print(f"[bold green]Updated:[/bold green] {path} = {value}")

    if components[0] == "domains":
        console.print(
            "\n[bold blue]Tip:[/bold blue] You've updated domain-specific trimming rules."
        )
        console.print(
            "These rules determine how HTML content is trimmed when converted to markdown."
        )


@app.command(name="get")
def get_config_value(
    path: str = typer.Argument(
        ..., help="Config path (e.g., 'domains.example.com.footer_marker')"
    ),
):
    """Get a configuration value at the specified path."""
    config = load_config()

    # Split the path into components
    components = path.split(".")

    # Navigate to the destination
    current = config
    for i, component in enumerate(components):
        if component not in current:
            console.print(
                f"[bold red]Error:[/bold red] Path '{path}' not found in configuration"
            )
            return
        elif i < len(components) - 1 and not isinstance(current[component], dict):
            console.print(
                f"[bold red]Error:[/bold red] '{'.'.join(components[:i+1])}' is not a dictionary"
            )
            return
        current = current[component]

    # Display the value
    json_str = json.dumps(current, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai")

    console.print(f"[bold blue]{path}:[/bold blue]")
    console.print(syntax)


@app.command(name="delete")
def delete_config_value(
    path: str = typer.Argument(
        ..., help="Config path to delete (e.g., 'domains.example.com')"
    ),
):
    """Delete a configuration value at the specified path."""
    config = load_config()

    # Split the path into components
    components = path.split(".")

    # Navigate to the parent
    current = config
    for i, component in enumerate(components[:-1]):
        if component not in current:
            console.print(
                f"[bold red]Error:[/bold red] Path '{path}' not found in configuration"
            )
            return
        elif not isinstance(current[component], dict):
            console.print(
                f"[bold red]Error:[/bold red] '{'.'.join(components[:i+1])}' is not a dictionary"
            )
            return
        current = current[component]

    # Delete the value
    last_component = components[-1]
    if last_component not in current:
        console.print(
            f"[bold red]Error:[/bold red] Path '{path}' not found in configuration"
        )
        return

    if Confirm.ask(f"Are you sure you want to delete '{path}'?"):
        deleted_value = current[last_component]
        del current[last_component]

        # Save the updated config
        CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

        console.print(f"[bold green]Deleted:[/bold green] {path}")
        console.print("[dim]Previous value was:[/dim]")
        json_str = json.dumps(deleted_value, indent=2)
        syntax = Syntax(json_str, "json", theme="monokai")
        console.print(syntax)


@app.command(name="add-domain")
def add_domain_config():
    """Interactive wizard to add domain-specific configuration."""
    config = load_config()

    # Domain name
    domain = Prompt.ask("[bold blue]Enter domain name[/bold blue] (e.g., example.com)")

    # Check if domain already exists
    if domain in config.get("domains", {}):
        if not Confirm.ask(
            f"Domain '{domain}' already exists. Do you want to update it?"
        ):
            return

    # Initialize domain config if it doesn't exist
    if "domains" not in config:
        config["domains"] = {}
    if domain not in config["domains"]:
        config["domains"][domain] = {}

    # Ask for footer marker
    if Confirm.ask(
        "Do you want to set a footer marker? (text that indicates where to trim content)"
    ):
        footer_marker = Prompt.ask("[bold blue]Enter footer marker text[/bold blue]")
        config["domains"][domain]["footer_marker"] = footer_marker

    # Ask for path-specific rules
    if Confirm.ask("Do you want to add path-specific rules?"):
        while True:
            path = Prompt.ask("[bold blue]Enter URL path[/bold blue] (e.g., /docs)")

            h1_occurrence = Prompt.ask(
                "[bold blue]Enter h1 occurrence to keep[/bold blue] (e.g., 2 means keep the 2nd h1 heading)",
                default="1",
            )

            path_footer = Prompt.ask(
                "[bold blue]Enter path-specific footer marker[/bold blue]", default=""
            )

            # Initialize path rules if they don't exist
            if "path_rules" not in config["domains"][domain]:
                config["domains"][domain]["path_rules"] = {}

            # Add path rule
            config["domains"][domain]["path_rules"][path] = {
                "h1_occurrence": int(h1_occurrence)
            }

            if path_footer:
                config["domains"][domain]["path_rules"][path][
                    "footer_marker"
                ] = path_footer

            if not Confirm.ask("Add another path rule?"):
                break

    # Save the config
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")

    # Show the updated domain config
    domain_config = config["domains"][domain]
    json_str = json.dumps({domain: domain_config}, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai")

    console.print("\n[bold green]Domain configuration added:[/bold green]")
    console.print(syntax)
    console.print(
        "\n[bold blue]Tip:[/bold blue] This configuration will be used when converting HTML from this domain."
    )


@app.command(name="list-domains")
def list_domains():
    """List all configured domains with their settings."""
    config = load_config()

    if "domains" not in config or not config["domains"]:
        console.print("[yellow]No domains configured yet.[/yellow]")
        console.print(
            "Use [bold]html2md config add-domain[/bold] to add domain configurations."
        )
        return

    # Create a table
    table = Table(title="Configured Domains")
    table.add_column("Domain", style="cyan")
    table.add_column("Footer Marker", style="green")
    table.add_column("Path Rules", style="magenta")

    # Add rows for each domain
    for domain, settings in config["domains"].items():
        footer = settings.get("footer_marker", "")

        path_rules_count = len(settings.get("path_rules", {}))
        path_rules = f"{path_rules_count} path rule(s)" if path_rules_count > 0 else ""

        table.add_row(domain, footer, path_rules)

    console.print(table)


@app.command(name="reset")
def reset_config():
    """Reset the configuration to default values."""
    if not Confirm.ask(
        "[bold red]Warning:[/bold red] This will reset all settings to default values. Continue?"
    ):
        return

    from html2md.config.loader import DEFAULT_CONFIG

    # Write default config
    CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")

    console.print("[bold green]Configuration reset to default values.[/bold green]")

    # Show the reset config
    json_str = json.dumps(DEFAULT_CONFIG, indent=2)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=True)

    console.print(Panel(syntax, title="Default Configuration", border_style="yellow"))


def entry_point():
    """Entry point for the CLI."""
    app()
