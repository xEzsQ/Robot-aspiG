import asyncio
import threading
import json
import tkinter as tk
from tkinter import messagebox
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "ELEGOO BT16"
UART_RX_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
UART_TX_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"

class RobotActiveScanApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Robot Active Scan - Elegoo")
        self.root.geometry("560x800")
        
        self.client = None
        self.is_connected = False
        self.is_moving_forward = False
        self.is_scanning = False
        self.cmd_counter = 1
        self.sequence_list = []
        self.last_servo_time = 0  # 👈 Initialisation de la variable manquante

        # Boucle d'événements asynchrone persistante en arrière-plan
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start_background_loop, daemon=True)
        self.thread.start()

        # --- Statut & Connexion ---
        self.lbl_status = tk.Label(root, text="Statut : Déconnecté 🔴", fg="red", font=("Arial", 11, "bold"))
        self.lbl_status.pack(pady=10)

        self.btn_connect = tk.Button(root, text="Connecter le Robot", command=self.toggle_connection, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), width=25, height=1)
        self.btn_connect.pack(pady=5)

        # --- Affichage des retours du capteur ---
        self.lbl_sensor = tk.Label(root, text="État du capteur : En attente...", fg="blue", font=("Arial", 10, "italic"))
        self.lbl_sensor.pack(pady=5)

        # --- Cadre Principal ---
        main_frame = tk.Frame(root)
        main_frame.pack(fill="both", expand=True, padx=15, pady=5)

        # --- Panneau Gauche : Moteurs, Tête & Scan ---
        left_panel = tk.Frame(main_frame)
        left_panel.pack(side="left", fill="both", expand=True, padx=5)

        # Moteurs Directs
        frame_ctrl = tk.LabelFrame(left_panel, text=" Mouvements Châssis ", font=("Arial", 10, "bold"))
        frame_ctrl.pack(fill="both", expand=True, pady=5)

        btn_fwd = tk.Button(frame_ctrl, text="▲ Avancer", width=10, height=2, command=lambda: self.send_json_cmd(3))
        btn_fwd.grid(row=0, column=1, pady=5)

        btn_left = tk.Button(frame_ctrl, text="◄ Gauche", width=10, height=2, command=lambda: self.send_json_cmd(1))
        btn_left.grid(row=1, column=0, padx=5, pady=5)

        btn_stop = tk.Button(frame_ctrl, text="■ STOP", width=10, height=2, bg="#f44336", fg="white", command=self.send_stop_cmd)
        btn_stop.grid(row=1, column=1, pady=5)

        btn_right = tk.Button(frame_ctrl, text="Droite ►", width=10, height=2, command=lambda: self.send_json_cmd(2))
        btn_right.grid(row=1, column=2, padx=5, pady=5)

        btn_back = tk.Button(frame_ctrl, text="▼ Reculer", width=10, height=2, command=lambda: self.send_json_cmd(4))
        btn_back.grid(row=2, column=1, pady=5)

        # Contrôle du Servo-moteur & Scan Actif
        frame_servo = tk.LabelFrame(left_panel, text=" Orientation & Balayage Actif ", font=("Arial", 10, "bold"))
        frame_servo.pack(fill="both", expand=True, pady=5)

        btn_look_left = tk.Button(frame_servo, text="⬅️ Gauche", width=10, bg="#9C27B0", fg="white", command=lambda: self.send_servo_angle(150))
        btn_look_left.grid(row=0, column=0, padx=2, pady=5)

        btn_look_center = tk.Button(frame_servo, text="⏺️ Centre", width=10, bg="#9C27B0", fg="white", command=lambda: self.send_servo_angle(90))
        btn_look_center.grid(row=0, column=1, padx=2, pady=5)

        btn_look_right = tk.Button(frame_servo, text="Droite ➡️", width=10, bg="#9C27B0", fg="white", command=lambda: self.send_servo_angle(30))
        btn_look_right.grid(row=0, column=2, padx=2, pady=5)

        # Bouton Activer/Désactiver le Scan Actif
        self.btn_toggle_scan = tk.Button(frame_servo, text="🔄 Activer Scan Actif (Radar)", width=32, bg="#FF9800", fg="white", font=("Arial", 9, "bold"), command=self.toggle_continuous_scan)
        self.btn_toggle_scan.grid(row=1, column=0, columnspan=3, padx=2, pady=5)

        # Paramètres & Vitesse
        frame_settings = tk.LabelFrame(left_panel, text=" Paramètres ", font=("Arial", 10, "bold"))
        frame_settings.pack(fill="both", expand=True, pady=5)

        tk.Label(frame_settings, text="Vitesse (0-250) :").pack(anchor="w", padx=5)
        self.entry_speed = tk.Entry(frame_settings, width=10, font=("Arial", 11))
        self.entry_speed.insert(0, "180")
        self.entry_speed.pack(anchor="w", padx=5, pady=2)

        # --- Panneau Droit : Séquence ---
        right_panel = tk.LabelFrame(main_frame, text=" Séquence Programmée ", font=("Arial", 10, "bold"))
        right_panel.pack(side="right", fill="both", expand=True, padx=5)

        seq_input_frame = tk.Frame(right_panel)
        seq_input_frame.pack(fill="x", padx=5, pady=5)

        tk.Label(seq_input_frame, text="Action :").pack(anchor="w")
        self.action_var = tk.StringVar(value="Avancer")
        actions_menu = tk.OptionMenu(seq_input_frame, self.action_var, "Avancer", "Reculer", "Gauche", "Droite")
        actions_menu.pack(fill="x", pady=2)

        tk.Label(seq_input_frame, text="Durée (secondes) :").pack(anchor="w", pady=(5, 0))
        self.entry_duration = tk.Entry(seq_input_frame, font=("Arial", 11))
        self.entry_duration.insert(0, "1.0")
        self.entry_duration.pack(fill="x", pady=2)

        btn_add_step = tk.Button(seq_input_frame, text="➕ Ajouter à la séquence", bg="#2196F3", fg="white", command=self.add_step)
        btn_add_step.pack(fill="x", pady=5)

        self.listbox_seq = tk.Listbox(right_panel, height=10, font=("Consolas", 9))
        self.listbox_seq.pack(fill="both", expand=True, padx=5, pady=5)

        btn_run_seq = tk.Button(right_panel, text="▶ Exécuter la Séquence", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), command=self.run_sequence)
        btn_run_seq.pack(fill="x", padx=5, pady=5)

        btn_clear_seq = tk.Button(right_panel, text="🗑 Effacer tout", bg="#9E9E9E", fg="white", command=self.clear_sequence)
        btn_clear_seq.pack(fill="x", padx=5, pady=2)

    def _start_background_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def toggle_connection(self):
        asyncio.run_coroutine_threadsafe(self._connect(), self.loop)

    async def _connect(self):
        try:
            self.lbl_status.config(text="Statut : Recherche du robot...", fg="orange")
            device = await BleakScanner.find_device_by_name(DEVICE_NAME)
            if not device:
                self.lbl_status.config(text="Statut : Robot introuvable ❌", fg="red")
                return

            self.client = BleakClient(device.address)
            await self.client.connect()
            
            if self.client.is_connected:
                def notification_handler(sender, data):
                    try:
                        decoded_msg = data.decode("utf-8", errors="ignore").strip()
                        self.root.after(0, lambda: self.process_sensor_data(decoded_msg))
                    except Exception as ex:
                        print(f"Erreur décodage : {ex}")

                await self.client.start_notify(UART_RX_UUID, notification_handler)

                self.is_connected = True
                self.lbl_status.config(text="Statut : Connecté ✓", fg="green")
                self.btn_connect.config(text="Connecté", state="disabled")
        except Exception as e:
            self.lbl_status.config(text=f"Statut : Erreur ({e})", fg="red")

    def process_sensor_data(self, msg):
        self.lbl_sensor.config(text=f"Capteur : {msg}")
        if "_true" in msg.lower() and self.is_moving_forward:
            print("⚠️ Obstacle détecté (_true) ! Arrêt d'urgence.")
            self.send_stop_cmd()
            self.lbl_sensor.config(text="🛑 ARRÊT D'URGENCE (Obstacle détecté)")

    def send_json_cmd(self, direction_code):
        if not self.is_connected:
            return
        try:
            speed = int(self.entry_speed.get())
        except ValueError:
            speed = 180

        self.is_moving_forward = (direction_code == 3)
        data = {"N": 40, "H": self.cmd_counter, "D1": direction_code, "D2": speed}
        self.cmd_counter = (self.cmd_counter % 99) + 1
        self.async_send(json.dumps(data))

    def send_servo_angle(self, angle):
        """Envoie l'angle au servo en utilisant N:6 (correspondant au case 6 de l'Arduino)"""
        if not self.is_connected:
            return
        
        import time
        current_time = time.time()
        if current_time - self.last_servo_time < 0.2:
            return
        self.last_servo_time = current_time

        # Utilisation de N:6 pour correspondre au code Arduino fourni
        data = {"N": 6, "H": self.cmd_counter, "D1": angle}
        self.cmd_counter = (self.cmd_counter % 99) + 1
        self.async_send(json.dumps(data))

    def toggle_continuous_scan(self):
        if not self.is_connected:
            messagebox.showwarning("Avertissement", "Non connecté au robot !")
            return
        
        if not self.is_scanning:
            self.is_scanning = True
            self.btn_toggle_scan.config(text="⏹️ Arrêter Scan Actif", bg="#F44336")
            asyncio.run_coroutine_threadsafe(self._active_scan_loop(), self.loop)
        else:
            self.is_scanning = False
            self.btn_toggle_scan.config(text="🔄 Activer Scan Actif (Radar)", bg="#FF9800")
            self.send_servo_angle(90)

    async def _active_scan_loop(self):
        """Boucle de balayage avec N:6 et interrogation active N:21"""
        angles = [45, 90, 135, 90]
        idx = 0
        while self.is_scanning and self.is_connected:
            angle = angles[idx]
            
            # 1. Orienter la tête (N:6)
            servo_data = {"N": 6, "H": self.cmd_counter, "D1": angle}
            self.cmd_counter = (self.cmd_counter % 99) + 1
            try:
                await self.client.write_gatt_char(UART_TX_UUID, json.dumps(servo_data).encode("utf-8"), response=True)
                await asyncio.sleep(0.15)
                
                # 2. Interroger activement le capteur à ultrasons (N:21)
                sensor_data = {"N": 21, "H": self.cmd_counter, "D1": 1}
                self.cmd_counter = (self.cmd_counter % 99) + 1
                await self.client.write_gatt_char(UART_TX_UUID, json.dumps(sensor_data).encode("utf-8"), response=True)

                # 3. Rafraîchir l'ordre d'avancer si le robot roule
                if self.is_moving_forward:
                    await asyncio.sleep(0.05)
                    try:
                        speed = int(self.entry_speed.get())
                    except ValueError:
                        speed = 180
                    move_data = {"N": 40, "H": self.cmd_counter, "D1": 3, "D2": speed}
                    self.cmd_counter = (self.cmd_counter % 99) + 1
                    await self.client.write_gatt_char(UART_TX_UUID, json.dumps(move_data).encode("utf-8"), response=True)

            except Exception as e:
                print(f"Erreur scan actif : {e}")
            
            idx = (idx + 1) % len(angles)
            await asyncio.sleep(0.3)

    def send_stop_cmd(self):
        if not self.is_connected:
            return
        self.is_moving_forward = False
        data = {"N": 5, "H": self.cmd_counter}
        self.cmd_counter = (self.cmd_counter % 99) + 1
        self.async_send(json.dumps(data))

    def add_step(self):
        action = self.action_var.get()
        try:
            duration = float(self.entry_duration.get())
        except ValueError:
            duration = 1.0
        
        dir_map = {"Avancer": 3, "Reculer": 4, "Gauche": 1, "Droite": 2}
        code = dir_map.get(action, 3)

        self.sequence_list.append({"action": action, "code": code, "duration": duration})
        self.listbox_seq.insert(tk.END, f"{action} ({duration}s)")

    def clear_sequence(self):
        self.sequence_list.clear()
        self.listbox_seq.delete(0, tk.END)

    def run_sequence(self):
        if not self.is_connected:
            messagebox.showwarning("Avertissement", "Non connecté au robot !")
            return
        if not self.sequence_list:
            messagebox.showinfo("Info", "La séquence est vide.")
            return

        asyncio.run_coroutine_threadsafe(self._execute_sequence_coro(), self.loop)

    async def _execute_sequence_coro(self):
        try:
            speed = int(self.entry_speed.get())
        except ValueError:
            speed = 180

        for step in self.sequence_list:
            self.is_moving_forward = (step["code"] == 3)

            data = {"N": 40, "H": self.cmd_counter, "D1": step["code"], "D2": speed}
            self.cmd_counter = (self.cmd_counter % 99) + 1
            await self.client.write_gatt_char(UART_TX_UUID, json.dumps(data).encode("utf-8"), response=True)
            await asyncio.sleep(step["duration"])

        self.is_moving_forward = False
        stop_data = {"N": 5, "H": self.cmd_counter}
        self.cmd_counter = (self.cmd_counter % 99) + 1
        await self.client.write_gatt_char(UART_TX_UUID, json.dumps(stop_data).encode("utf-8"), response=True)

    def async_send(self, text):
        async def task():
            await self.client.write_gatt_char(UART_TX_UUID, text.encode("utf-8"), response=True)
        
        if self.is_connected:
            asyncio.run_coroutine_threadsafe(task(), self.loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = RobotActiveScanApp(root)
    root.mainloop()
