import { Tabs } from 'expo-router';
import { View, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

type IoniconsName = React.ComponentProps<typeof Ionicons>['name'];

type TabConfig = {
  name: string;
  title: string;
  icon: IoniconsName;
  iconFocused: IoniconsName;
  isCenter?: boolean;
};

const TABS: TabConfig[] = [
  {
    name: 'index',
    title: 'Dashboard',
    icon: 'home-outline',
    iconFocused: 'home',
  },
  {
    name: 'approvals',
    title: 'Approvals',
    icon: 'checkmark-circle-outline',
    iconFocused: 'checkmark-circle',
  },
  {
    name: 'capture',
    title: 'Capture',
    icon: 'camera-outline',
    iconFocused: 'camera',
    isCenter: true,
  },
  {
    name: 'transactions',
    title: 'Transactions',
    icon: 'list-outline',
    iconFocused: 'list',
  },
  {
    name: 'assistant',
    title: 'Assistant',
    icon: 'sparkles-outline',
    iconFocused: 'sparkles',
  },
];

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarStyle: styles.tabBar,
        tabBarActiveTintColor: '#6366f1',
        tabBarInactiveTintColor: '#64748b',
        tabBarLabelStyle: styles.tabLabel,
      }}
    >
      {TABS.map((tab) => (
        <Tabs.Screen
          key={tab.name}
          name={tab.name}
          options={{
            title: tab.title,
            tabBarIcon: ({ focused, color }) => {
              if (tab.isCenter) {
                return (
                  <View style={styles.centerIcon}>
                    <Ionicons
                      name={focused ? tab.iconFocused : tab.icon}
                      size={26}
                      color="#fff"
                    />
                  </View>
                );
              }
              return (
                <Ionicons
                  name={focused ? tab.iconFocused : tab.icon}
                  size={22}
                  color={color}
                />
              );
            },
            tabBarLabel: tab.isCenter ? '' : tab.title,
          }}
        />
      ))}
    </Tabs>
  );
}

const styles = StyleSheet.create({
  tabBar: {
    backgroundColor: '#0f172a',
    borderTopColor: '#1e293b',
    borderTopWidth: 1,
    height: 80,
    paddingBottom: 12,
    paddingTop: 8,
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: '500',
  },
  centerIcon: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#6366f1',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
    shadowColor: '#6366f1',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 8,
  },
});
