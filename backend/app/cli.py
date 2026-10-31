"""Commandes d'administration : uv run python -m app.cli --help"""

import typer

from app import accounts
from app.db import SessionLocal
from app.models import Role
from app.security import MIN_PASSWORD_LENGTH

cli = typer.Typer(no_args_is_help=True)


@cli.callback()
def main() -> None:
    """Commandes d'administration de RunningStats."""


@cli.command()
def create_admin(
    email: str = typer.Option(..., prompt=True),
    display_name: str = typer.Option(..., prompt="Nom affiché"),
    password: str = typer.Option(
        ..., prompt="Mot de passe", hide_input=True, confirmation_prompt=True
    ),
) -> None:
    """Crée un compte admin (le premier membre du groupe)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise typer.BadParameter(f"{MIN_PASSWORD_LENGTH} caractères minimum.")
    with SessionLocal() as db:
        try:
            user = accounts.create_user(
                db, display_name=display_name, email=email, password=password, role=Role.admin
            )
        except accounts.AccessError as e:
            typer.echo(e.message, err=True)
            raise typer.Exit(1) from e
        db.commit()
        typer.echo(f"Admin créé : {user.email} (id {user.id})")


if __name__ == "__main__":
    cli()
