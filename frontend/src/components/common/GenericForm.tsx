"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import {
  useForm,
  type FieldValues,
  type Path,
  type SubmitHandler,
  type UseFormReturn,
} from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface FormFieldConfig<T extends FieldValues> {
  name: Path<T>;
  label: string;
  type:
    | "text"
    | "email"
    | "password"
    | "date"
    | "datetime-local"
    | "time"
    | "number"
    | "select";
  placeholder?: string;
  description?: string;
  multiple?: boolean;
  options?: { value: string; label: string }[];
  disabled?: boolean;
  transform?: {
    toInput?: (value: unknown) => string;
    fromInput?: (value: string | string[]) => unknown;
  };
}

interface GenericFormProps<T extends FieldValues> {
  schema: z.ZodType<T>;
  defaultValues: T;
  fields: FormFieldConfig<T>[];
  onSubmit: SubmitHandler<T>;
  submitButtonText: string;
  cancelButtonText?: string;
  onCancel?: () => void;
  disabled?: boolean;
  className?: string;
}

function GenericForm<T extends FieldValues>({
  schema,
  defaultValues,
  fields,
  onSubmit,
  submitButtonText,
  cancelButtonText,
  onCancel,
  disabled = false,
  className = "grid gap-4",
}: GenericFormProps<T>) {
  const form = useForm({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(schema as any),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    defaultValues: defaultValues as any,
  }) as UseFormReturn<T>;

  const handleSelectChange = (
    field: { value: unknown; onChange: (value: unknown) => void },
    fieldConfig: FormFieldConfig<T>,
    value: string
  ) => {
    if (fieldConfig.multiple) {
      const current = Array.isArray(field.value) ? field.value : [];
      const newValues = current.includes(value)
        ? current.filter((v: string) => v !== value)
        : [...current, value];
      field.onChange(
        fieldConfig.transform?.fromInput
          ? fieldConfig.transform.fromInput(newValues)
          : newValues
      );
    } else {
      field.onChange(
        fieldConfig.transform?.fromInput
          ? fieldConfig.transform.fromInput(value)
          : value
      );
    }
  };

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className={className}
        aria-disabled={disabled}
      >
        {fields.map((fieldConfig) => (
          <FormField
            key={fieldConfig.name}
            control={form.control}
            name={fieldConfig.name}
            render={({ field }) => (
              <FormItem>
                <FormLabel>{fieldConfig.label}</FormLabel>
                <FormControl>
                  {fieldConfig.type === "select" ? (
                    <Select
                      onValueChange={(value) =>
                        handleSelectChange(field, fieldConfig, value)
                      }
                      value={
                        fieldConfig.multiple
                          ? undefined
                          : fieldConfig.transform?.toInput
                          ? fieldConfig.transform.toInput(field.value)
                          : (field.value as string)
                      }
                      disabled={fieldConfig.disabled || disabled}
                    >
                      <SelectTrigger>
                        <SelectValue
                          placeholder={
                            fieldConfig.placeholder || "Select an option"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {fieldConfig.options?.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      type={fieldConfig.type}
                      placeholder={fieldConfig.placeholder}
                      {...field}
                      value={
                        fieldConfig.transform?.toInput
                          ? fieldConfig.transform.toInput(field.value)
                          : field.value ?? ""
                      }
                      onChange={(e) =>
                        field.onChange(
                          fieldConfig.transform?.fromInput
                            ? fieldConfig.transform.fromInput(e.target.value)
                            : e.target.value
                        )
                      }
                      disabled={fieldConfig.disabled || disabled}
                    />
                  )}
                </FormControl>
                {fieldConfig.description && (
                  <FormDescription>{fieldConfig.description}</FormDescription>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
        ))}
        <div className="flex gap-2">
          <Button
            type="submit"
            disabled={disabled || form.formState.isSubmitting}
          >
            {form.formState.isSubmitting ? "Submitting..." : submitButtonText}
          </Button>
          {cancelButtonText && onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={disabled || form.formState.isSubmitting}
            >
              {cancelButtonText}
            </Button>
          )}
        </div>
      </form>
    </Form>
  );
}

export default GenericForm;
export type { FormFieldConfig };
