import styles from "./auth.module.css";

interface FormAlertProps {
  tone: "error" | "success" | "info";
  title: string;
  message: string;
  reference?: string | null;
}

const ICONS = {
  error: "!",
  success: "✓",
  info: "i",
} as const;

export function FormAlert({ tone, title, message, reference }: FormAlertProps) {
  return (
    <div
      className={`${styles.alert} ${styles[tone]}`}
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
    >
      <span className={styles.alertIcon} aria-hidden="true">
        {ICONS[tone]}
      </span>
      <div>
        <strong>{title}</strong>
        <p>{message}</p>
        {reference ? <small>Destek referansı: {reference}</small> : null}
      </div>
    </div>
  );
}
