import React, { useState, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  TextInput,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { accountsApi, expenseClaimsApi, type AccountRow } from '@/lib/api';

const expenseSchema = z.object({
  amount: z.string().min(1, 'Amount is required').regex(/^\d+(\.\d{1,2})?$/, 'Enter a valid amount'),
  description: z.string().min(1, 'Description is required'),
  account_id: z.string().min(1, 'Select an account'),
});

type ExpenseForm = z.infer<typeof expenseSchema>;

export default function CaptureScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const [showCamera, setShowCamera] = useState(false);
  const [photoUri, setPhotoUri] = useState<string | null>(null);
  const cameraRef = useRef<CameraView>(null);
  const qc = useQueryClient();

  const { data: accounts } = useQuery<AccountRow[]>({
    queryKey: ['accounts'],
    queryFn: accountsApi.list,
  });

  const {
    control,
    handleSubmit,
    reset,
    watch,
    setValue,
    formState: { errors },
  } = useForm<ExpenseForm>({
    resolver: zodResolver(expenseSchema),
    defaultValues: { amount: '', description: '', account_id: '' },
  });

  const selectedAccountId = watch('account_id');

  const createClaim = useMutation({
    mutationFn: (values: ExpenseForm) =>
      expenseClaimsApi.create({
        description: values.description,
        currency: 'USD',
        lines: [
          {
            account_id: values.account_id,
            description: values.description,
            amount: values.amount,
            ...(photoUri ? { receipt_url: photoUri } : {}),
          },
        ],
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['expenseClaims'] });
      reset();
      setPhotoUri(null);
      Alert.alert('Success', 'Expense claim created successfully.');
    },
    onError: (err: Error) => {
      Alert.alert('Error', err.message);
    },
  });

  const takePicture = async () => {
    if (!cameraRef.current) return;
    const photo = await cameraRef.current.takePictureAsync({ quality: 0.7 });
    if (photo) {
      setPhotoUri(photo.uri);
      setShowCamera(false);
    }
  };

  const pickImage = async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.7,
    });
    if (!result.canceled && result.assets[0]) {
      setPhotoUri(result.assets[0].uri);
    }
  };

  const openCamera = async () => {
    if (!permission?.granted) {
      const { granted } = await requestPermission();
      if (!granted) {
        Alert.alert('Permission required', 'Camera access is needed to capture receipts.');
        return;
      }
    }
    setShowCamera(true);
  };

  if (showCamera) {
    return (
      <View style={styles.cameraContainer}>
        <CameraView ref={cameraRef} style={styles.camera} facing="back">
          <View style={styles.cameraOverlay}>
            <TouchableOpacity
              style={styles.closeBtn}
              onPress={() => setShowCamera(false)}
            >
              <Text style={styles.closeBtnText}>✕ Cancel</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.shutterBtn} onPress={takePicture}>
              <View style={styles.shutterInner} />
            </TouchableOpacity>
          </View>
        </CameraView>
      </View>
    );
  }

  // Expense accounts (type 5xxx or account_type === 'expense')
  const expenseAccounts = (accounts ?? []).filter(
    (a) => a.account_type === 'expense' || a.code.startsWith('5'),
  );

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.headerTitle}>Capture Receipt</Text>

          {/* Photo section */}
          <View style={styles.photoSection}>
            {photoUri ? (
              <View style={styles.previewContainer}>
                <Image source={{ uri: photoUri }} style={styles.preview} />
                <TouchableOpacity
                  style={styles.clearPhoto}
                  onPress={() => setPhotoUri(null)}
                >
                  <Text style={styles.clearPhotoText}>Remove</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <View style={styles.photoButtons}>
                <TouchableOpacity
                  style={styles.photoBtn}
                  onPress={openCamera}
                  activeOpacity={0.7}
                >
                  <Text style={styles.photoBtnIcon}>📷</Text>
                  <Text style={styles.photoBtnText}>Take Photo</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={styles.photoBtn}
                  onPress={pickImage}
                  activeOpacity={0.7}
                >
                  <Text style={styles.photoBtnIcon}>🖼</Text>
                  <Text style={styles.photoBtnText}>Choose from Library</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* Form */}
          <View style={styles.form}>
            <Text style={styles.label}>Amount (USD)</Text>
            <Controller
              control={control}
              name="amount"
              render={({ field: { onChange, onBlur, value } }) => (
                <TextInput
                  style={[styles.input, errors.amount ? styles.inputError : null]}
                  placeholder="0.00"
                  placeholderTextColor="#64748b"
                  keyboardType="decimal-pad"
                  onBlur={onBlur}
                  onChangeText={onChange}
                  value={value}
                />
              )}
            />
            {errors.amount ? (
              <Text style={styles.fieldError}>{errors.amount.message}</Text>
            ) : null}

            <Text style={[styles.label, styles.labelSpacing]}>Description</Text>
            <Controller
              control={control}
              name="description"
              render={({ field: { onChange, onBlur, value } }) => (
                <TextInput
                  style={[styles.input, errors.description ? styles.inputError : null]}
                  placeholder="e.g. Client lunch, Office supplies"
                  placeholderTextColor="#64748b"
                  onBlur={onBlur}
                  onChangeText={onChange}
                  value={value}
                />
              )}
            />
            {errors.description ? (
              <Text style={styles.fieldError}>{errors.description.message}</Text>
            ) : null}

            <Text style={[styles.label, styles.labelSpacing]}>Category (Account)</Text>
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.accountPicker}
            >
              {expenseAccounts.length === 0 ? (
                <Text style={styles.noAccountsText}>Loading accounts…</Text>
              ) : (
                expenseAccounts.map((acc) => (
                  <TouchableOpacity
                    key={acc.id}
                    style={[
                      styles.accountChip,
                      selectedAccountId === acc.id ? styles.accountChipActive : null,
                    ]}
                    onPress={() => setValue('account_id', acc.id)}
                  >
                    <Text
                      style={[
                        styles.accountChipText,
                        selectedAccountId === acc.id
                          ? styles.accountChipTextActive
                          : null,
                      ]}
                    >
                      {acc.code} {acc.name}
                    </Text>
                  </TouchableOpacity>
                ))
              )}
            </ScrollView>
            {errors.account_id ? (
              <Text style={styles.fieldError}>{errors.account_id.message}</Text>
            ) : null}

            <TouchableOpacity
              style={[
                styles.submitBtn,
                createClaim.isPending ? styles.submitBtnDisabled : null,
              ]}
              onPress={handleSubmit((v) => createClaim.mutate(v))}
              disabled={createClaim.isPending}
              activeOpacity={0.8}
            >
              {createClaim.isPending ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.submitBtnText}>Create Expense Claim</Text>
              )}
            </TouchableOpacity>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  flex: {
    flex: 1,
  },
  scroll: {
    padding: 20,
    paddingBottom: 60,
  },
  headerTitle: {
    fontSize: 26,
    fontWeight: '700',
    color: '#e2e8f0',
    marginBottom: 20,
  },
  cameraContainer: {
    flex: 1,
    backgroundColor: '#000',
  },
  camera: {
    flex: 1,
  },
  cameraOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    paddingBottom: 40,
    paddingHorizontal: 20,
    gap: 20,
    alignItems: 'center',
  },
  closeBtn: {
    position: 'absolute',
    top: 60,
    left: 20,
    backgroundColor: 'rgba(0,0,0,0.5)',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
  },
  closeBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  shutterBtn: {
    width: 70,
    height: 70,
    borderRadius: 35,
    borderWidth: 4,
    borderColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterInner: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: '#fff',
  },
  photoSection: {
    marginBottom: 20,
  },
  previewContainer: {
    alignItems: 'center',
    gap: 10,
  },
  preview: {
    width: '100%',
    height: 200,
    borderRadius: 10,
    resizeMode: 'cover',
  },
  clearPhoto: {
    paddingVertical: 6,
    paddingHorizontal: 14,
    backgroundColor: '#450a0a',
    borderRadius: 6,
  },
  clearPhotoText: {
    color: '#fca5a5',
    fontSize: 13,
    fontWeight: '500',
  },
  photoButtons: {
    flexDirection: 'row',
    gap: 12,
  },
  photoBtn: {
    flex: 1,
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 16,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#334155',
    gap: 6,
  },
  photoBtnIcon: {
    fontSize: 24,
  },
  photoBtnText: {
    color: '#94a3b8',
    fontSize: 13,
    fontWeight: '500',
    textAlign: 'center',
  },
  form: {
    gap: 0,
  },
  label: {
    fontSize: 14,
    fontWeight: '500',
    color: '#94a3b8',
    marginBottom: 6,
  },
  labelSpacing: {
    marginTop: 16,
  },
  input: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: '#e2e8f0',
  },
  inputError: {
    borderColor: '#ef4444',
  },
  fieldError: {
    color: '#f87171',
    fontSize: 12,
    marginTop: 4,
  },
  accountPicker: {
    flexGrow: 0,
  },
  accountChip: {
    backgroundColor: '#1e293b',
    borderWidth: 1,
    borderColor: '#334155',
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 7,
    marginRight: 8,
  },
  accountChipActive: {
    backgroundColor: '#312e81',
    borderColor: '#6366f1',
  },
  accountChipText: {
    fontSize: 13,
    color: '#94a3b8',
    fontWeight: '500',
  },
  accountChipTextActive: {
    color: '#a5b4fc',
  },
  noAccountsText: {
    color: '#64748b',
    fontSize: 13,
    paddingVertical: 8,
  },
  submitBtn: {
    backgroundColor: '#6366f1',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: 28,
  },
  submitBtnDisabled: {
    opacity: 0.6,
  },
  submitBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
});
