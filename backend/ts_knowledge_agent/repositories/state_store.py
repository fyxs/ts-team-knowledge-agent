from __future__ import annotations
import sqlite3
from pathlib import Path
from ts_knowledge_agent.services.scanner import SourceFile

class StateStore:
    def __init__(self,path:Path)->None:
        self.path=path; self.path.parent.mkdir(parents=True,exist_ok=True); self.connection=sqlite3.connect(self.path); self.connection.row_factory=sqlite3.Row; self._init_schema()
    def _init_schema(self)->None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS sources(relative_path TEXT PRIMARY KEY,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS conversions(relative_path TEXT PRIMARY KEY,source_sha256 TEXT NOT NULL,output_path TEXT NOT NULL,converter_version TEXT NOT NULL,status TEXT NOT NULL,error_message TEXT,reason TEXT,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
        columns={row[1] for row in self.connection.execute("PRAGMA table_info(conversions)")}
        if "reason" not in columns: self.connection.execute("ALTER TABLE conversions ADD COLUMN reason TEXT")
        self.connection.commit()
    def upsert_source(self,source:SourceFile,status:str="discovered")->None:
        self.connection.execute("""INSERT INTO sources(relative_path,size,mtime_ns,sha256,status) VALUES(?,?,?,?,?) ON CONFLICT(relative_path) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns,sha256=excluded.sha256,status=excluded.status,updated_at=CURRENT_TIMESTAMP""",(source.relative_path,source.size,source.mtime_ns,source.sha256,status)); self.connection.commit()
    def update_source_status(self,relative_path:str,status:str)->None:
        self.connection.execute("UPDATE sources SET status=?,updated_at=CURRENT_TIMESTAMP WHERE relative_path=?",(status,relative_path))
        self.connection.commit()
    def mark_missing_sources(self,seen_paths:set[str])->int:
        rows=self.connection.execute("SELECT relative_path FROM sources").fetchall(); missing=[r["relative_path"] for r in rows if r["relative_path"] not in seen_paths]
        if missing: self.connection.executemany("UPDATE sources SET status='source_missing',updated_at=CURRENT_TIMESTAMP WHERE relative_path=?",[(p,) for p in missing]); self.connection.commit()
        return len(missing)
    def list_sources(self)->list[sqlite3.Row]: return list(self.connection.execute("SELECT * FROM sources ORDER BY relative_path"))
    def recover_stale_processing(self,stale_minutes:int=60)->int:
        cur=self.connection.execute("UPDATE conversions SET status='failed_retryable',reason='stale_processing_recovered',error_message=COALESCE(error_message,'processing interrupted before completion'),updated_at=CURRENT_TIMESTAMP WHERE status='processing' AND updated_at < datetime('now', ?)",(f'-{stale_minutes} minutes',)); self.connection.commit(); return cur.rowcount
    def conversion_reason(self,source:SourceFile)->str:
        row=self.connection.execute("SELECT source_sha256,status,output_path FROM conversions WHERE relative_path=?",(source.relative_path,)).fetchone()
        if row is None: return "new_source"
        if row["source_sha256"]!=source.sha256: return "source_changed"
        if row["status"]!="converted": return "previous_failed"
        if not Path(row["output_path"]).is_file(): return "output_missing"
        return "unchanged"
    def needs_conversion(self,source:SourceFile)->bool: return self.conversion_reason(source)!="unchanged"
    def record_conversion(self,relative_path:str,source_sha256:str,output_path:Path,converter_version:str,status:str,error_message:str|None=None,reason:str|None=None)->None:
        self.connection.execute("""INSERT INTO conversions(relative_path,source_sha256,output_path,converter_version,status,error_message,reason) VALUES(?,?,?,?,?,?,?) ON CONFLICT(relative_path) DO UPDATE SET source_sha256=excluded.source_sha256,output_path=excluded.output_path,converter_version=excluded.converter_version,status=excluded.status,error_message=excluded.error_message,reason=excluded.reason,updated_at=CURRENT_TIMESTAMP""",(relative_path,source_sha256,str(output_path),converter_version,status,error_message,reason)); self.connection.commit()
    def list_conversions(self)->list[sqlite3.Row]: return list(self.connection.execute("SELECT * FROM conversions ORDER BY relative_path"))
    def close(self)->None: self.connection.close()
