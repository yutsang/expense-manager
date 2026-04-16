import React, { useState } from 'react';
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { billsApi, expenseClaimsApi, type Bill, type ExpenseClaim } from '@/lib/api';

type Tab = 'bills' | 'expense-claims';

function StatusBadge({ status }: { status: string }) {
  const isApproved = status === 'approved';
  const isPending = status === 'pending' || status === 'submitted';
  return (
    <View
      style={[
        styles.badge,
        isApproved
          ? styles.badgeApproved
          : isPending
            ? styles.badgePending
            : styles.badgeDefault,
      ]}
    >
      <Text style={styles.badgeText}>{status}</Text>
    </View>
  );
}

function BillRow({
  item,
  onApprove,
  approving,
}: {
  item: Bill;
  onApprove: (id: string) => void;
  approving: boolean;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowMain}>
        <View style={styles.rowLeft}>
          <Text style={styles.rowTitle} numberOfLines={1}>
            {item.vendor_name ?? 'Unknown vendor'}
          </Text>
          <Text style={styles.rowSub}>
            Due {dayjs(item.due_date).format('MMM D, YYYY')}
          </Text>
        </View>
        <View style={styles.rowRight}>
          <Text style={styles.rowAmount}>
            {item.currency} {item.total_amount}
          </Text>
          <StatusBadge status={item.status} />
        </View>
      </View>
      {item.status === 'pending' || item.status === 'submitted' ? (
        <TouchableOpacity
          style={[styles.approveBtn, approving ? styles.approveBtnDisabled : null]}
          onPress={() => onApprove(item.id)}
          disabled={approving}
          activeOpacity={0.7}
        >
          {approving ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Text style={styles.approveBtnText}>Approve</Text>
          )}
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

function ExpenseClaimRow({
  item,
  onApprove,
  approving,
}: {
  item: ExpenseClaim;
  onApprove: (id: string) => void;
  approving: boolean;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.rowMain}>
        <View style={styles.rowLeft}>
          <Text style={styles.rowTitle} numberOfLines={1}>
            {item.description}
          </Text>
          <Text style={styles.rowSub}>
            {item.created_by} · {dayjs(item.created_at).format('MMM D')}
          </Text>
        </View>
        <View style={styles.rowRight}>
          <Text style={styles.rowAmount}>
            {item.currency} {item.total_amount}
          </Text>
          <StatusBadge status={item.status} />
        </View>
      </View>
      {item.status === 'submitted' ? (
        <TouchableOpacity
          style={[styles.approveBtn, approving ? styles.approveBtnDisabled : null]}
          onPress={() => onApprove(item.id)}
          disabled={approving}
          activeOpacity={0.7}
        >
          {approving ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Text style={styles.approveBtnText}>Approve</Text>
          )}
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

export default function ApprovalsScreen() {
  const [activeTab, setActiveTab] = useState<Tab>('bills');
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const qc = useQueryClient();

  const {
    data: bills,
    isLoading: billsLoading,
    refetch: refetchBills,
  } = useQuery({ queryKey: ['bills'], queryFn: billsApi.list });

  const {
    data: claims,
    isLoading: claimsLoading,
    refetch: refetchClaims,
  } = useQuery({ queryKey: ['expenseClaims'], queryFn: expenseClaimsApi.list });

  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([refetchBills(), refetchClaims()]);
    setRefreshing(false);
  };

  const approveBill = useMutation({
    mutationFn: (id: string) => billsApi.approve(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bills'] });
      setApprovingId(null);
    },
    onError: (err: Error) => {
      setApprovingId(null);
      Alert.alert('Approval failed', err.message);
    },
  });

  const approveClaim = useMutation({
    mutationFn: (id: string) => expenseClaimsApi.approve(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['expenseClaims'] });
      setApprovingId(null);
    },
    onError: (err: Error) => {
      setApprovingId(null);
      Alert.alert('Approval failed', err.message);
    },
  });

  const handleApproveBill = (id: string) => {
    setApprovingId(id);
    approveBill.mutate(id);
  };

  const handleApproveClaim = (id: string) => {
    setApprovingId(id);
    approveClaim.mutate(id);
  };

  const isLoading = activeTab === 'bills' ? billsLoading : claimsLoading;
  const billsList = bills ?? [];
  const claimsList = claims ?? [];

  return (
    <SafeAreaView style={styles.safe}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Approvals</Text>
      </View>

      {/* Tabs */}
      <View style={styles.tabRow}>
        <TouchableOpacity
          style={[styles.tabBtn, activeTab === 'bills' ? styles.tabBtnActive : null]}
          onPress={() => setActiveTab('bills')}
        >
          <Text
            style={[
              styles.tabBtnText,
              activeTab === 'bills' ? styles.tabBtnTextActive : null,
            ]}
          >
            Bills
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[
            styles.tabBtn,
            activeTab === 'expense-claims' ? styles.tabBtnActive : null,
          ]}
          onPress={() => setActiveTab('expense-claims')}
        >
          <Text
            style={[
              styles.tabBtnText,
              activeTab === 'expense-claims' ? styles.tabBtnTextActive : null,
            ]}
          >
            Expense Claims
          </Text>
        </TouchableOpacity>
      </View>

      {isLoading ? (
        <ActivityIndicator color="#6366f1" style={styles.loader} />
      ) : activeTab === 'bills' ? (
        <FlatList<Bill>
          data={billsList}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <BillRow
              item={item}
              onApprove={handleApproveBill}
              approving={approvingId === item.id}
            />
          )}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#6366f1"
            />
          }
          ListEmptyComponent={
            <Text style={styles.emptyText}>No bills awaiting approval.</Text>
          }
        />
      ) : (
        <FlatList<ExpenseClaim>
          data={claimsList}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <ExpenseClaimRow
              item={item}
              onApprove={handleApproveClaim}
              approving={approvingId === item.id}
            />
          )}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={onRefresh}
              tintColor="#6366f1"
            />
          }
          ListEmptyComponent={
            <Text style={styles.emptyText}>No expense claims awaiting approval.</Text>
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: '#0f172a',
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 8,
  },
  headerTitle: {
    fontSize: 26,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  tabRow: {
    flexDirection: 'row',
    marginHorizontal: 20,
    marginBottom: 16,
    backgroundColor: '#1e293b',
    borderRadius: 8,
    padding: 3,
    gap: 3,
  },
  tabBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 6,
  },
  tabBtnActive: {
    backgroundColor: '#6366f1',
  },
  tabBtnText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748b',
  },
  tabBtnTextActive: {
    color: '#fff',
  },
  loader: {
    marginTop: 40,
  },
  list: {
    paddingHorizontal: 20,
    paddingBottom: 40,
    gap: 10,
  },
  row: {
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 14,
    gap: 10,
  },
  rowMain: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  rowLeft: {
    flex: 1,
    marginRight: 12,
  },
  rowTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#e2e8f0',
    marginBottom: 3,
  },
  rowSub: {
    fontSize: 12,
    color: '#64748b',
  },
  rowRight: {
    alignItems: 'flex-end',
    gap: 4,
  },
  rowAmount: {
    fontSize: 15,
    fontWeight: '700',
    color: '#e2e8f0',
  },
  badge: {
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  badgeApproved: {
    backgroundColor: '#14532d',
  },
  badgePending: {
    backgroundColor: '#1e3a5f',
  },
  badgeDefault: {
    backgroundColor: '#1e293b',
  },
  badgeText: {
    fontSize: 10,
    fontWeight: '600',
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  approveBtn: {
    backgroundColor: '#6366f1',
    borderRadius: 7,
    paddingVertical: 9,
    alignItems: 'center',
  },
  approveBtnDisabled: {
    opacity: 0.6,
  },
  approveBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  emptyText: {
    color: '#64748b',
    fontSize: 14,
    textAlign: 'center',
    paddingVertical: 40,
  },
});
