"""Production research service entry point, separate from the API container."""
import asyncio

async def main():
    from app.disclosure import install_log_redaction
    from app.db.connection import init_db,close_db
    from app.research_jobs import ResearchDispatcher
    install_log_redaction()
    await init_db()
    dispatcher=ResearchDispatcher();dispatcher.start()
    try:await dispatcher.task
    finally:
        await dispatcher.stop();await close_db()

if __name__=='__main__':asyncio.run(main())
