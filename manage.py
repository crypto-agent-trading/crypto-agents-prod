import asyncio, typer
from app.api.main import manager
import uvicorn

cli = typer.Typer(add_completion=False)

@cli.command()
def server(host: str="0.0.0.0", port: int=8000):
    uvicorn.run("app.api.main:app", host=host, port=port, reload=False)

@cli.command("list")
def list_agents():
    for a in manager.list():
        print(a)

@cli.command("start-all")
def start_all():
    asyncio.run(manager.start_all())

@cli.command("stop-all")
def stop_all():
    asyncio.run(manager.stop_all())

if __name__ == "__main__":
    cli()
