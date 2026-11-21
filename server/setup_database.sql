-- ONE-TIME setup, run as the PostgreSQL superuser ("postgres"). Creates:
--   * the login role "assistant" (the backend connects with it)
--   * the database "voice_assistant", owned by "assistant"
--   * the pgvector extension inside it (needs superuser, so it is done here, not in a migration)
--
-- Run from server\ (choose your own password, and put the same one in server\.env):
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -v db_password=YOUR_PASSWORD -f setup_database.sql
--
-- Tables are NOT created here: they come from the files in migrations/ (python -m app.migrate).

CREATE ROLE assistant LOGIN PASSWORD :'db_password';
CREATE DATABASE voice_assistant OWNER assistant ENCODING 'UTF8';

\connect voice_assistant
CREATE EXTENSION IF NOT EXISTS vector;
