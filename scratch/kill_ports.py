import psutil

ports_to_kill = [8081, 5050, 8765, 8766, 8767]
killed = []

for proc in psutil.process_iter(['pid', 'name']):
    try:
        # Kill node.exe
        if proc.info['name'] == 'node.exe':
            proc.kill()
            killed.append(f"node.exe (PID {proc.info['pid']})")
            continue
            
        # Kill processes on specific ports
        for conn in proc.connections(kind='inet'):
            if conn.laddr.port in ports_to_kill:
                proc.kill()
                killed.append(f"{proc.info['name']} (PID {proc.info['pid']} on port {conn.laddr.port})")
                break
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

print("Killed processes:", killed)
