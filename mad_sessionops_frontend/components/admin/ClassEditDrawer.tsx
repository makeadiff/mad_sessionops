"use client";

import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import MenuItem from "@mui/material/MenuItem";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import {
  createClass,
  updateClass,
  type AdminClass,
  type ClassInput,
} from "@/lib/api/services/catalog.service";
import type { ApiRejection } from "@/lib/api/client";
import {
  BORDER,
  FieldLabel,
  MUTED,
  Notice,
  SidePanel,
  TEXT,
  dangerButtonSx,
  fieldSx,
  primaryButtonSx,
  secondaryButtonSx,
} from "./adminUi";

// Shape validation only — next-class/cycle/in-use rules are enforced server-side.
const schema = z.object({
  classCode: z.string().trim().min(1, "Code is required").max(4, "At most 4 characters"),
  className: z.string().trim().min(1, "Name is required").max(20, "At most 20 characters"),
  nextClassId: z.number().nullable(),
  openForEnrolment: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

const NONE = "none";
const FORM_ID = "class-edit-form";

export interface ClassEditDrawerProps {
  open: boolean;
  /** null = add a new class */
  editing: AdminClass | null;
  classes: AdminClass[];
  onClose: () => void;
  onSaved: (saved: AdminClass) => void;
}

export function ClassEditDrawer({
  open,
  editing,
  classes,
  onClose,
  onSaved,
}: ClassEditDrawerProps) {
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      classCode: "",
      className: "",
      nextClassId: null,
      openForEnrolment: true,
    },
  });

  useEffect(() => {
    if (!open) return;
    reset(
      editing
        ? {
            classCode: editing.classCode,
            className: editing.className,
            nextClassId: editing.nextClassId,
            openForEnrolment: editing.openForEnrolment,
          }
        : {
            classCode: "",
            className: "",
            nextClassId: null,
            openForEnrolment: true,
          }
    );
  }, [open, editing, classes, reset]);

  const nextOptions = classes.filter((c) => c.isActive && c.classId !== editing?.classId);

  const onSubmit = async (values: FormValues) => {
    setServerError(null);
    const input: ClassInput = { ...values };
    try {
      const saved = editing ? await updateClass(editing.classId, input) : await createClass(input);
      onSaved(saved);
    } catch (caught) {
      setServerError((caught as Partial<ApiRejection>)?.message || "Could not save the class.");
    }
  };

  const toggleActive = async () => {
    if (!editing) return;
    setServerError(null);
    try {
      onSaved(await updateClass(editing.classId, { isActive: !editing.isActive }));
    } catch (caught) {
      setServerError((caught as Partial<ApiRejection>)?.message || "Could not update the class.");
    }
  };

  // Clear any server error on close so the next open starts clean.
  const close = () => {
    setServerError(null);
    onClose();
  };

  return (
    <SidePanel
      open={open}
      onClose={close}
      width={400}
      closeLabel="Close"
      title={editing ? `Edit ${editing.className}` : "Add class"}
      subtitle={
        editing
          ? `Used by ${editing.inUseCount} ${editing.inUseCount === 1 ? "school" : "schools"}`
          : "Add a class to the catalog"
      }
      footer={
        <>
          {editing && (
            <Button
              variant="outlined"
              size="small"
              onClick={toggleActive}
              disabled={isSubmitting}
              sx={{ ...(editing.isActive ? dangerButtonSx : secondaryButtonSx), mr: "auto" }}
            >
              {editing.isActive ? "Deactivate" : "Reactivate"}
            </Button>
          )}
          <Button
            variant="outlined"
            size="small"
            onClick={close}
            disabled={isSubmitting}
            sx={secondaryButtonSx}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form={FORM_ID}
            variant="contained"
            size="small"
            disabled={isSubmitting}
            sx={{ ...primaryButtonSx, minWidth: 96 }}
          >
            {isSubmitting ? (
              <CircularProgress size={14} color="inherit" />
            ) : editing ? (
              "Save"
            ) : (
              "Add class"
            )}
          </Button>
        </>
      }
    >
      <Box
        component="form"
        id={FORM_ID}
        onSubmit={handleSubmit(onSubmit)}
        noValidate
        sx={{ display: "flex", flexDirection: "column", gap: 2 }}
      >
        {serverError && <Notice tone="error">{serverError}</Notice>}

        <Box sx={{ display: "grid", gridTemplateColumns: "1fr 110px", gap: 1.5 }}>
          <Box>
            <FieldLabel htmlFor="class-name" required>
              Class name
            </FieldLabel>
            <Controller
              name="className"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  id="class-name"
                  placeholder="e.g. 9th"
                  size="small"
                  fullWidth
                  error={!!errors.className}
                  helperText={errors.className?.message}
                  sx={fieldSx}
                />
              )}
            />
          </Box>
          <Box>
            <FieldLabel htmlFor="class-code" required>
              Code
            </FieldLabel>
            <Controller
              name="classCode"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  id="class-code"
                  placeholder="e.g. 9"
                  size="small"
                  fullWidth
                  error={!!errors.classCode}
                  helperText={errors.classCode?.message}
                  sx={fieldSx}
                />
              )}
            />
          </Box>
        </Box>

        <Box>
          <FieldLabel id="next-class-label">Next class</FieldLabel>
          <Controller
            name="nextClassId"
            control={control}
            render={({ field }) => (
              <TextField
                select
                size="small"
                fullWidth
                value={field.value === null ? NONE : String(field.value)}
                onChange={(e) =>
                  field.onChange(e.target.value === NONE ? null : Number(e.target.value))
                }
                SelectProps={{ labelId: "next-class-label" }}
                helperText="Where year progression moves this class's children. It also sets the order classes are listed in."
                sx={fieldSx}
              >
                <MenuItem value={NONE} sx={{ fontSize: "13px" }}>
                  None — children stay in this class
                </MenuItem>
                {nextOptions.map((c) => (
                  <MenuItem key={c.classId} value={String(c.classId)} sx={{ fontSize: "13px" }}>
                    {c.className}
                  </MenuItem>
                ))}
              </TextField>
            )}
          />
        </Box>

        <Controller
          name="openForEnrolment"
          control={control}
          render={({ field }) => (
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 2,
                border: `1px solid ${BORDER}`,
                borderRadius: "8px",
                px: 1.75,
                py: 1.25,
              }}
            >
              <Box>
                <Typography
                  component="label"
                  htmlFor="class-open"
                  sx={{ fontSize: "13px", fontWeight: 600, color: TEXT }}
                >
                  Open for new enrolment
                </Typography>
                <Typography sx={{ fontSize: "11px", color: MUTED, mt: 0.25 }}>
                  When off, COs can&apos;t enrol children into this class or add it to a school.
                </Typography>
              </Box>
              <Switch
                id="class-open"
                checked={field.value}
                onChange={(_, v) => field.onChange(v)}
              />
            </Box>
          )}
        />
      </Box>
    </SidePanel>
  );
}

export default ClassEditDrawer;
