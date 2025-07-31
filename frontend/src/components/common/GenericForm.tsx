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
  type: "text" | "email" | "password" | "date" | "datetime-local" | "select";
  placeholder?: string;
  description?: string;
  multiple?: boolean;
  options?: { value: string; label: string }[];
}

interface GenericFormProps<T extends FieldValues> {
  schema: z.ZodType<T>;
  defaultValues: T;
  fields: FormFieldConfig<T>[];
  onSubmit: SubmitHandler<T>;
  submitButtonText: string;
}

function GenericForm<T extends FieldValues>({
  schema,
  defaultValues,
  fields,
  onSubmit,
  submitButtonText,
}: GenericFormProps<T>) {
  const form = useForm({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(schema as any),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    defaultValues: defaultValues as any,
  }) as UseFormReturn<T>;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-4">
        {fields.map((field) => (
          <FormField
            key={field.name}
            control={form.control}
            name={field.name}
            render={({ field: formField }) => (
              <FormItem>
                <FormLabel>{field.label}</FormLabel>
                <FormControl>
                  {field.type === "select" ? (
                    <Select
                      onValueChange={(value) => {
                        if (field.multiple) {
                          const current = Array.isArray(formField.value)
                            ? formField.value
                            : [];
                          formField.onChange([...current, value]);
                        } else {
                          formField.onChange(value);
                        }
                      }}
                      value={
                        field.multiple && Array.isArray(formField.value)
                          ? undefined
                          : formField.value
                      }
                      defaultValue={
                        field.multiple ? undefined : formField.value
                      }
                    >
                      <SelectTrigger>
                        <SelectValue
                          placeholder={field.placeholder || "Select an option"}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {field.options?.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      type={field.type}
                      placeholder={field.placeholder}
                      {...formField}
                      value={formField.value ?? ""}
                    />
                  )}
                </FormControl>
                {field.description && (
                  <p className="text-muted-foreground text-sm">
                    {field.description}
                  </p>
                )}
                <FormMessage />
              </FormItem>
            )}
          />
        ))}
        <Button type="submit">{submitButtonText}</Button>
      </form>
    </Form>
  );
}

export default GenericForm;
export type { FormFieldConfig };
