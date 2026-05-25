"""CLI front door for package-backed configuration commands."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Literal

from harnify_coding_agent.cli.config_selector import select_config
from harnify_coding_agent.config import APP_NAME, PACKAGE_NAME, get_agent_dir, get_update_instruction
from harnify_coding_agent.core.package_manager import DefaultPackageManager
from harnify_coding_agent.core.settings_manager import SettingsManager


PackageCommand = Literal["install", "remove", "update", "list"]
UpdateTargetType = Literal["all", "self", "extensions"]


@dataclass(slots=True)
class UpdateTarget:
    type: UpdateTargetType
    source: str | None = None


@dataclass(slots=True)
class PackageCommandOptions:
    command: PackageCommand
    source: str | None = None
    updateTarget: UpdateTarget | None = None
    local: bool = False
    force: bool = False
    help: bool = False
    invalidOption: str | None = None
    invalidArgument: str | None = None
    missingOptionValue: str | None = None
    conflictingOptions: str | None = None


_command_exit_code = 0


def _set_command_exit_code(code: int) -> None:
    global _command_exit_code
    _command_exit_code = code


def _take_command_exit_code() -> int:
    global _command_exit_code
    code = _command_exit_code
    _command_exit_code = 0
    return code


def _get_package_command_usage(command: PackageCommand) -> str:
    match command:
        case "install":
            return f"{APP_NAME} install <source> [-l]"
        case "remove":
            return f"{APP_NAME} remove <source> [-l]"
        case "update":
            return f"{APP_NAME} update [source|self|pi] [--self] [--extensions] [--extension <source>] [--force]"
        case "list":
            return f"{APP_NAME} list"


def _parse_package_command(args: list[str]) -> PackageCommandOptions | None:
    if not args:
        return None

    raw_command = args[0]
    command: PackageCommand | None = None
    if raw_command == "uninstall":
        command = "remove"
    elif raw_command in {"install", "remove", "update", "list"}:
        command = raw_command
    if command is None:
        return None

    options = PackageCommandOptions(command=command)
    remainder = args[1:]
    self_flag = False
    extensions_flag = False
    extension_flag_source: str | None = None
    index = 0
    while index < len(remainder):
        arg = remainder[index]
        if arg in {"-h", "--help"}:
            options.help = True
        elif arg in {"-l", "--local"}:
            if command in {"install", "remove"}:
                options.local = True
            elif options.invalidOption is None:
                options.invalidOption = arg
        elif arg == "--self":
            if command == "update":
                self_flag = True
            elif options.invalidOption is None:
                options.invalidOption = arg
        elif arg == "--extensions":
            if command == "update":
                extensions_flag = True
            elif options.invalidOption is None:
                options.invalidOption = arg
        elif arg == "--force":
            if command == "update":
                options.force = True
            elif options.invalidOption is None:
                options.invalidOption = arg
        elif arg == "--extension":
            if command != "update":
                if options.invalidOption is None:
                    options.invalidOption = arg
            else:
                value = remainder[index + 1] if index + 1 < len(remainder) else None
                if value is None or value.startswith("-"):
                    if options.missingOptionValue is None:
                        options.missingOptionValue = arg
                elif extension_flag_source is not None:
                    if options.conflictingOptions is None:
                        options.conflictingOptions = "--extension can only be provided once"
                    index += 1
                else:
                    extension_flag_source = value
                    index += 1
        elif arg.startswith("-"):
            if options.invalidOption is None:
                options.invalidOption = arg
        elif options.source is None:
            options.source = arg
        elif options.invalidArgument is None:
            options.invalidArgument = arg
        index += 1

    if command == "update":
        if extension_flag_source is not None:
            if self_flag or extensions_flag:
                options.conflictingOptions = (
                    options.conflictingOptions
                    or "--extension cannot be combined with --self or --extensions"
                )
            if options.source:
                options.conflictingOptions = (
                    options.conflictingOptions
                    or "--extension cannot be combined with a positional source"
                )
            options.updateTarget = UpdateTarget(type="extensions", source=extension_flag_source)
        elif options.source:
            source_is_self = options.source in {"self", "pi"}
            if source_is_self:
                options.updateTarget = UpdateTarget(type="all" if extensions_flag else "self")
            else:
                if extensions_flag or self_flag:
                    options.conflictingOptions = (
                        options.conflictingOptions
                        or "positional update targets cannot be combined with --self or --extensions"
                    )
                options.updateTarget = UpdateTarget(type="extensions", source=options.source)
        elif self_flag and extensions_flag:
            options.updateTarget = UpdateTarget(type="all")
        elif self_flag:
            options.updateTarget = UpdateTarget(type="self")
        elif extensions_flag:
            options.updateTarget = UpdateTarget(type="extensions")
        else:
            options.updateTarget = UpdateTarget(type="all")

    return options


def _print_package_command_help(command: PackageCommand) -> None:
    app_name = PACKAGE_NAME.replace("-coding-agent", "")
    if command == "install":
        print(f"Usage: {app_name} install <source> [-l|--local]")
        return
    if command == "remove":
        print(f"Usage: {app_name} remove <source> [-l|--local]")
        print(f"Alias: {app_name} uninstall <source> [-l|--local]")
        return
    if command == "update":
        print(f"Usage: {app_name} update [source|self|pi] [--self] [--extensions]")
        return
    print(f"Usage: {app_name} list")


async def handle_config_command(args: list[str]) -> int | None:
    if not args or args[0] != "config":
        return None
    _set_command_exit_code(0)

    cwd = os.getcwd()
    agent_dir = get_agent_dir()
    settings_manager = SettingsManager.create(cwd, agent_dir)
    package_manager = DefaultPackageManager(
        {
            "cwd": cwd,
            "agentDir": agent_dir,
            "settingsManager": settings_manager,
        }
    )
    resolved_paths = await package_manager.resolve()
    await select_config(
        {
            "resolvedPaths": resolved_paths,
            "settingsManager": settings_manager,
            "cwd": cwd,
            "agentDir": agent_dir,
        }
    )
    return True


async def handle_package_command(args: list[str]) -> int | None:
    parsed = _parse_package_command(args)
    if parsed is None:
        return None
    _set_command_exit_code(0)

    if parsed.help:
        _print_package_command_help(parsed.command)
        return True

    if parsed.invalidOption:
        print(f'Unknown option {parsed.invalidOption} for "{parsed.command}".', file=sys.stderr)
        print(f'Use "{APP_NAME} --help" or "{_get_package_command_usage(parsed.command)}".', file=sys.stderr)
        _set_command_exit_code(1)
        return True

    if parsed.missingOptionValue:
        print(f"Missing value for {parsed.missingOptionValue}.", file=sys.stderr)
        print(f"Usage: {_get_package_command_usage(parsed.command)}", file=sys.stderr)
        _set_command_exit_code(1)
        return True

    if parsed.invalidArgument:
        print(f"Unexpected argument {parsed.invalidArgument}.", file=sys.stderr)
        print(f"Usage: {_get_package_command_usage(parsed.command)}", file=sys.stderr)
        _set_command_exit_code(1)
        return True

    if parsed.conflictingOptions:
        print(parsed.conflictingOptions, file=sys.stderr)
        print(f"Usage: {_get_package_command_usage(parsed.command)}", file=sys.stderr)
        _set_command_exit_code(1)
        return True

    cwd = os.getcwd()
    agent_dir = get_agent_dir()
    settings_manager = SettingsManager.create(cwd, agent_dir)
    package_manager = DefaultPackageManager(
        {
            "cwd": cwd,
            "agentDir": agent_dir,
            "settingsManager": settings_manager,
        }
    )

    try:
        if parsed.command == "list":
            packages = package_manager.listConfiguredPackages()
            if not packages:
                print("No packages configured.")
                return True
            for package in packages:
                scope = "local" if package.scope == "project" else package.scope
                installed = package.installedPath or "<not installed>"
                print(f"{package.source}\t{scope}\t{installed}")
            return True

        if parsed.command == "install":
            if not parsed.source:
                print("Error: install requires a source argument", file=sys.stderr)
                _set_command_exit_code(1)
                return True
            await package_manager.installAndPersist(parsed.source, {"local": parsed.local})
            return True

        if parsed.command == "remove":
            if not parsed.source:
                print("Error: remove requires a source argument", file=sys.stderr)
                _set_command_exit_code(1)
                return True
            await package_manager.removeAndPersist(parsed.source, {"local": parsed.local})
            return True

        if parsed.command == "update":
            target = parsed.updateTarget or UpdateTarget(type="all")
            update_self = target.type in {"all", "self"}
            update_extensions = target.type in {"all", "extensions"}

            if update_self:
                print(get_update_instruction(PACKAGE_NAME))
            if update_extensions:
                extension_target = target.source if target.type == "extensions" else None
                await package_manager.update(extension_target)
            return True
    except Exception as error:  # noqa: BLE001
        print(f"Error: {error}", file=sys.stderr)
        _set_command_exit_code(1)
        return True

    return True


handleConfigCommand = handle_config_command
handlePackageCommand = handle_package_command

__all__ = [
    "PackageCommand",
    "handleConfigCommand",
    "handlePackageCommand",
]
