import { useCallback, useState } from "react";

export type FormErrors<T extends object> = Partial<Record<keyof T, string>>;

export interface UseAuthFormOptions<T extends object> {
  initialValues: T;
  validate: (values: T) => FormErrors<T>;
  onValid: (values: T) => void;
}

export function useAuthForm<T extends object>({
  initialValues,
  validate,
  onValid,
}: UseAuthFormOptions<T>) {
  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<FormErrors<T>>({});

  const setField = useCallback((field: keyof T, value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }));
    setErrors((prev) => (prev[field] ? { ...prev, [field]: undefined } : prev));
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      const nextErrors = validate(values);
      setErrors(nextErrors);
      if (Object.values(nextErrors).every((message) => !message)) {
        onValid(values);
      }
    },
    [values, validate, onValid]
  );

  return { values, errors, setField, handleSubmit };
}
