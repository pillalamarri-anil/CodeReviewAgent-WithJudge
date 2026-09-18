package com.example.service;

import com.example.repository.OrderRepository;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public BigDecimal totalForCustomer(long customerId, List<Long> orderIds) {
        BigDecimal total = BigDecimal.ZERO;
        for (Long id : orderIds) {
            Order order = orderRepository.findById(id).orElseThrow();
            total = total.add(order.getAmount());
        }
        return total;
    }

    public Order placeOrder(long customerId, BigDecimal amount) {
        Order order = new Order();
        order.setCustomerId(customerId);
        order.setAmount(amount);
        return orderRepository.save(order);
    }
}
