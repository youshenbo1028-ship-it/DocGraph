
import json, time, webview
r={}
def main():
    w=webview.create_window("d", html='<html><body>hi</body></html>', frameless=True, width=400, height=200)
    def on():
        time.sleep(1)
        try:
            r['hwnd'] = int(w.native.Handle.ToInt32())
        except Exception as e:
            r['err'] = str(e)
        w.destroy()
    w.events.loaded+=on
    webview.start(); print(json.dumps(r))
main()
