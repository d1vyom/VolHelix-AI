import React, { useEffect, useState } from 'react';
import { io } from 'socket.io-client';

type LogEntry = {
  agent: string;
  message: string;
  level: string;
};

const AuditLog: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([]);

  useEffect(() => {
    const s = io(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
    s.on('agent_log', (payload: LogEntry) => {
      setLogs(prev => [...prev, payload]);
    });
    return () => {
      s.disconnect();
    };
  }, []);

  return (
    <div className="max-h-64 overflow-auto bg-gray-50 p-2 rounded border">
      {logs.length === 0 && <p className="text-sm text-gray-500">No logs yet.</p>}
      <ul className="space-y-1 text-sm">
        {logs.map((log, idx) => (
          <li key={idx} className={`flex justify-between ${log.level === 'ERROR' ? 'text-red-600' : 'text-gray-800'}`}>
            <span>[{log.agent}] {log.message}</span>
            <span className="opacity-60">{log.level}</span>
          </li>
        ))}
      </ul>
    </div>
  );
};

export default AuditLog;
