use glib::ControlFlow;
use gtk::prelude::*;
use gtk::{
    Application, ApplicationWindow, Box as GtkBox, Button, DropDown, FileDialog, Label,
    Orientation, ScrolledWindow, TextBuffer, TextView,
};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::thread;

const APP_ID: &str = "com.locatelli.stl-repair-gui";
const MODE_IDS: [&str; 2] = ["print", "gentle"];

fn project_root() -> PathBuf {
    if let Ok(root) = std::env::var("STL_REPAIR_ROOT") {
        return PathBuf::from(root);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if dir.ends_with("release") || dir.ends_with("debug") {
                if let Some(p) = dir.parent().and_then(|d| d.parent()) {
                    let candidate = p.join("python/repair_mesh.py");
                    if candidate.exists() {
                        return p.to_path_buf();
                    }
                }
            }
            let candidate = dir.join("python/repair_mesh.py");
            if candidate.exists() {
                return dir.to_path_buf();
            }
        }
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn python_executable(root: &Path) -> PathBuf {
    if let Ok(py) = std::env::var("STL_REPAIR_PYTHON") {
        return PathBuf::from(py);
    }
    let venv = root.join(".venv/bin/python3");
    if venv.exists() {
        return venv;
    }
    PathBuf::from("python3")
}

fn script_path(root: &Path) -> PathBuf {
    root.join("python/repair_mesh.py")
}

fn mode_from_dropdown(dropdown: &DropDown) -> String {
    MODE_IDS
        .get(dropdown.selected() as usize)
        .unwrap_or(&MODE_IDS[0])
        .to_string()
}

fn default_output(input: &Path, mode: &str) -> PathBuf {
    let stem = input.file_stem().and_then(|s| s.to_str()).unwrap_or("model");
    let suffix = match mode {
        "print" => "_print",
        "gentle" => "_repaired",
        _ => "_print",
    };
    input
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join(format!("{stem}{suffix}.stl"))
}

fn append_log(buffer: &TextBuffer, text: &str) {
    let mut end = buffer.end_iter();
    buffer.insert(&mut end, text);
    if !text.ends_with('\n') {
        let mut end = buffer.end_iter();
        buffer.insert(&mut end, "\n");
    }
}

fn pick_file(window: &ApplicationWindow, save: bool) -> Option<PathBuf> {
    let dialog = FileDialog::builder().modal(true).build();
    let filter = gtk::FileFilter::new();
    filter.set_name(Some("Malhas 3D"));
    filter.add_mime_type("model/stl");
    filter.add_pattern("*.stl");
    filter.add_pattern("*.3mf");
    filter.add_pattern("*.glb");
    filter.add_pattern("*.gltf");
    let filters = gtk::gio::ListStore::new::<gtk::FileFilter>();
    filters.append(&filter);
    dialog.set_filters(Some(&filters));
    if save {
        dialog.set_initial_name(Some("modelo_reparado.stl"));
    }

    let (tx, rx) = mpsc::channel();
    if save {
        dialog.save(
            Some(window),
            None::<&gtk::gio::Cancellable>,
            move |result| {
                let _ = tx.send(result.ok().and_then(|f| f.path()));
            },
        );
    } else {
        dialog.open(
            Some(window),
            None::<&gtk::gio::Cancellable>,
            move |result| {
                let _ = tx.send(result.ok().and_then(|f| f.path()));
            },
        );
    }

    while rx.try_recv().is_err() {
        while glib::MainContext::default().iteration(false) {}
    }
    rx.try_recv().ok().flatten()
}

fn run_repair(
    input: PathBuf,
    output: PathBuf,
    mode: String,
    log_tx: mpsc::Sender<String>,
) -> Result<(), String> {
    let root = project_root();
    let python = python_executable(&root);
    let script = script_path(&root);

    if !script.exists() {
        return Err(format!("Script não encontrado: {}", script.display()));
    }
    if !python.exists() && python.as_os_str() == "python3" {
        log_tx
            .send("Aviso: usando python3 do sistema; rode ./setup.sh se faltar dependências.".into())
            .ok();
    }

    log_tx
        .send(format!("Python: {}", python.display()))
        .ok();
    log_tx
        .send(format!("Script: {}", script.display()))
        .ok();

    let mut child = Command::new(&python)
        .arg(&script)
        .arg("--input")
        .arg(&input)
        .arg("--output")
        .arg(&output)
        .arg("--mode")
        .arg(&mode)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("Falha ao iniciar Python: {e}"))?;

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    if let Some(out) = stdout {
        use std::io::{BufRead, BufReader};
        for line in BufReader::new(out).lines().map_while(Result::ok) {
            let _ = log_tx.send(line);
        }
    }
    if let Some(err) = stderr {
        use std::io::{BufRead, BufReader};
        for line in BufReader::new(err).lines().map_while(Result::ok) {
            let _ = log_tx.send(format!("[stderr] {line}"));
        }
    }

    let status = child.wait().map_err(|e| format!("Erro ao aguardar Python: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!(
            "Reparo terminou com código {}",
            status.code().unwrap_or(-1)
        ))
    }
}

fn main() {
    let app = Application::builder().application_id(APP_ID).build();

    app.connect_activate(|app| {
        let root = project_root();
        let python = python_executable(&root);

        let window = ApplicationWindow::builder()
            .application(app)
            .title("STL Repair — Reparo de Malhas 3D")
            .default_width(720)
            .default_height(560)
            .build();

        let vbox = GtkBox::new(Orientation::Vertical, 12);
        vbox.set_margin_top(16);
        vbox.set_margin_bottom(16);
        vbox.set_margin_start(16);
        vbox.set_margin_end(16);

        let subtitle = Label::new(Some(
            "Selecione um STL/3MF, escolha o modo de reparo e clique em Reparar.",
        ));
        subtitle.add_css_class("dim-label");
        subtitle.set_halign(gtk::Align::Start);
        subtitle.set_wrap(true);
        vbox.append(&subtitle);

        let input_row = GtkBox::new(Orientation::Horizontal, 8);
        let input_label = Label::new(Some("Entrada:"));
        input_label.set_width_chars(10);
        input_label.set_halign(gtk::Align::Start);
        input_label.set_xalign(0.0);
        let input_path_label = Label::new(Some("(nenhum arquivo)"));
        input_path_label.set_halign(gtk::Align::Start);
        input_path_label.set_xalign(0.0);
        input_path_label.set_hexpand(true);
        input_path_label.set_ellipsize(gtk::pango::EllipsizeMode::Middle);
        input_path_label.add_css_class("monospace");
        let pick_input_btn = Button::with_label("Escolher…");
        input_row.append(&input_label);
        input_row.append(&input_path_label);
        input_row.append(&pick_input_btn);
        vbox.append(&input_row);

        let output_row = GtkBox::new(Orientation::Horizontal, 8);
        let output_label = Label::new(Some("Saída:"));
        output_label.set_width_chars(10);
        output_label.set_halign(gtk::Align::Start);
        output_label.set_xalign(0.0);
        let output_path_label = Label::new(Some("(automático)"));
        output_path_label.set_halign(gtk::Align::Start);
        output_path_label.set_xalign(0.0);
        output_path_label.set_hexpand(true);
        output_path_label.set_ellipsize(gtk::pango::EllipsizeMode::Middle);
        output_path_label.add_css_class("monospace");
        let pick_output_btn = Button::with_label("Salvar como…");
        output_row.append(&output_label);
        output_row.append(&output_path_label);
        output_row.append(&pick_output_btn);
        vbox.append(&output_row);

        let mode_row = GtkBox::new(Orientation::Horizontal, 8);
        let mode_label = Label::new(Some("Modo:"));
        mode_label.set_width_chars(10);
        mode_label.set_halign(gtk::Align::Start);
        mode_label.set_xalign(0.0);
        let mode_dropdown = DropDown::from_strings(&[
            "Print — watertight (alpha wrap, recomendado)",
            "Gentle — reparo leve (não garante watertight)",
        ]);
        mode_dropdown.set_selected(0);
        mode_dropdown.set_hexpand(true);
        mode_row.append(&mode_label);
        mode_row.append(&mode_dropdown);
        vbox.append(&mode_row);

        let action_row = GtkBox::new(Orientation::Horizontal, 8);
        let repair_btn = Button::builder()
            .label("Reparar")
            .css_classes(["suggested-action"])
            .build();
        let status_label = Label::new(Some("Pronto."));
        status_label.set_halign(gtk::Align::Start);
        status_label.set_hexpand(true);
        action_row.append(&repair_btn);
        action_row.append(&status_label);
        vbox.append(&action_row);

        let log_label = Label::new(Some("Log:"));
        log_label.set_halign(gtk::Align::Start);
        vbox.append(&log_label);

        let log_view = TextView::new();
        log_view.set_editable(false);
        log_view.set_monospace(true);
        log_view.set_vexpand(true);
        let log_buffer = log_view.buffer().clone();
        let scroll = ScrolledWindow::builder()
            .child(&log_view)
            .hexpand(true)
            .vexpand(true)
            .min_content_height(220)
            .build();
        vbox.append(&scroll);

        let info = Label::new(Some(&format!(
            "Projeto: {}  |  Python: {}",
            root.display(),
            python.display()
        )));
        info.add_css_class("caption");
        info.set_halign(gtk::Align::Start);
        info.set_wrap(true);
        vbox.append(&info);

        window.set_child(Some(&vbox));

        let input_path = std::rc::Rc::new(std::cell::RefCell::new(None::<PathBuf>));
        let output_path = std::rc::Rc::new(std::cell::RefCell::new(None::<PathBuf>));
        let custom_output = std::rc::Rc::new(std::cell::RefCell::new(false));

        {
            let window = window.clone();
            let input_path = input_path.clone();
            let output_path = output_path.clone();
            let custom_output = custom_output.clone();
            let input_path_label = input_path_label.clone();
            let output_path_label = output_path_label.clone();
            let mode_dropdown = mode_dropdown.clone();
            pick_input_btn.connect_clicked(move |_| {
                if let Some(path) = pick_file(&window, false) {
                    input_path_label.set_text(&path.display().to_string());
                    *input_path.borrow_mut() = Some(path.clone());
                    if !*custom_output.borrow() {
                        let mode = mode_from_dropdown(&mode_dropdown);
                        let out = default_output(&path, &mode);
                        output_path_label.set_text(&out.display().to_string());
                        *output_path.borrow_mut() = Some(out);
                    }
                }
            });
        }

        {
            let window = window.clone();
            let output_path = output_path.clone();
            let custom_output = custom_output.clone();
            let output_path_label = output_path_label.clone();
            pick_output_btn.connect_clicked(move |_| {
                if let Some(path) = pick_file(&window, true) {
                    output_path_label.set_text(&path.display().to_string());
                    *output_path.borrow_mut() = Some(path);
                    *custom_output.borrow_mut() = true;
                }
            });
        }

        {
            let input_path = input_path.clone();
            let output_path = output_path.clone();
            let custom_output = custom_output.clone();
            let output_path_label = output_path_label.clone();
            mode_dropdown.connect_selected_notify(move |dropdown| {
                if *custom_output.borrow() {
                    return;
                }
                if let Some(input) = input_path.borrow().clone() {
                    let mode = mode_from_dropdown(dropdown);
                    let out = default_output(&input, &mode);
                    output_path_label.set_text(&out.display().to_string());
                    *output_path.borrow_mut() = Some(out);
                }
            });
        }

        {
            let input_path = input_path.clone();
            let output_path = output_path.clone();
            let pick_input_btn = pick_input_btn.clone();
            let pick_output_btn = pick_output_btn.clone();
            let status_label = status_label.clone();
            let log_buffer = log_buffer.clone();
            let mode_dropdown = mode_dropdown.clone();
            let repair_btn_connect = repair_btn.clone();
            let repair_btn_action = repair_btn.clone();
            repair_btn_connect.connect_clicked(move |_| {
                let input = match input_path.borrow().clone() {
                    Some(p) => p,
                    None => {
                        status_label.set_text("Selecione um arquivo de entrada.");
                        return;
                    }
                };
                let mode = mode_from_dropdown(&mode_dropdown);
                let output = output_path
                    .borrow()
                    .clone()
                    .unwrap_or_else(|| default_output(&input, &mode));

                repair_btn_action.set_sensitive(false);
                pick_input_btn.set_sensitive(false);
                pick_output_btn.set_sensitive(false);
                status_label.set_text("Reparando… (pode levar alguns minutos)");
                log_buffer.set_text("");

                append_log(&log_buffer, &format!("Iniciando reparo: {}", input.display()));

                let (tx, rx) = mpsc::channel::<String>();
                let input_clone = input.clone();
                let output_clone = output.clone();
                let mode_clone = mode.clone();

                thread::spawn(move || {
                    let result = run_repair(input_clone, output_clone.clone(), mode_clone, tx.clone());
                    let status = if result.is_ok() { "ok" } else { "err" };
                    let _ = tx.send(format!("__DONE__|{status}|{}", output_clone.display()));
                });

                let repair_btn_done = repair_btn_action.clone();
                let pick_input_btn = pick_input_btn.clone();
                let pick_output_btn = pick_output_btn.clone();
                let status_label = status_label.clone();
                let log_buffer = log_buffer.clone();
                glib::timeout_add_local(std::time::Duration::from_millis(120), move || {
                    while let Ok(line) = rx.try_recv() {
                        if let Some(rest) = line.strip_prefix("__DONE__|") {
                            let ok = rest.starts_with("ok|");
                            status_label.set_text(if ok {
                                "Concluído com sucesso!"
                            } else {
                                "Concluído com erros — veja o log."
                            });
                            repair_btn_done.set_sensitive(true);
                            pick_input_btn.set_sensitive(true);
                            pick_output_btn.set_sensitive(true);
                            return ControlFlow::Break;
                        }
                        append_log(&log_buffer, &line);
                    }
                    ControlFlow::Continue
                });
            });
        }

        window.present();
    });

    app.run();
}
